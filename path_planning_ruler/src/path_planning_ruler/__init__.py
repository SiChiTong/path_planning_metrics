import rospy
import tf
from tf.transformations import quaternion_from_euler, euler_from_quaternion
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal, MoveBaseFeedback
from actionlib import SimpleActionClient
from actionlib_msgs.msg import GoalStatus
from geometry_msgs.msg import Pose2D, Twist, PoseStamped, Point32, Polygon
from nav_msgs.msg import Path, OccupancyGrid
from map_msgs.msg import OccupancyGridUpdate
from path_planning_simulation import *
from sensor_msgs.msg import PointCloud2
from gazebo_msgs.msg import ModelStates
from std_srvs.srv import Empty
import people_msgs.msg
import std_msgs.msg
import traceback, sys
import yaml

#from path_planning_analysis.msg import CycleTimes
#from costmap_2d.msg import CycleTimesG

def finished(state):
    return state==GoalStatus.SUCCEEDED or state==GoalStatus.ABORTED or state==GoalStatus.PREEMPTED

def get_time_and_pose(tf, f1, f2):
    try:
        t = tf.getLatestCommonTime(f1, f2)
        pos, q = tf.lookupTransform(f1, f2, t)
    except:
        traceback.print_exc(file=sys.stdout)
        return None, None

    rpy = euler_from_quaternion(q)
    return t, Pose2D(pos[0], pos[1], rpy[2])

class MoveBaseClient:
    global_tf = None

    def __init__(self, record_rate=5, timeout=90):
        if MoveBaseClient.global_tf is None:
            MoveBaseClient.global_tf = tf.TransformListener()
        self.tf = MoveBaseClient.global_tf
        self.ac = SimpleActionClient('move_base', MoveBaseAction)
        self.record_rate = record_rate
        self.base_frame = '/map'
        self.target_frame = '/base_footprint'
        self.timeout = rospy.Duration( timeout )

        self.recording = False
        self.other_data = []

        self.subscriptions = []
        self.subscribers = []

        printed = False
        limit = rospy.Time.now() + rospy.Duration(30)
        while not self.ac.wait_for_server(rospy.Duration(5.0)) and not rospy.is_shutdown() and rospy.Time.now() < limit:
            printed = True
            rospy.loginfo('Waiting for move_base server')
            
        if rospy.Time.now() >= limit:
            self.ac = None
            return

        if rospy.is_shutdown():
            self.ac = None
            return

        if printed:
            rospy.loginfo('Got move_base server')
        
    def ready(self):
        return self.ac is not None

    def addSubscription(self, topic, msg_type):
        self.subscriptions.append( (topic, msg_type) )

    def reset(self):
        for name, proxy in self.resets.iteritems():
            proxy()
            rospy.loginfo("Reset called on %s"%name)

    def cb(self, msg, topic):
        if not self.recording:
            return

        if topic == '/move_base_node/DWAPlannerROS/local_plan':
            msg.header.frame_id = '/map'
            for i, pose in enumerate(msg.poses):
                msg.poses[i] = self.tf.transformPose('/map', pose)
        elif topic == '/move_base_node/local_costmap/costmap':
            p = PoseStamped()
            p.header = msg.header
            p.pose = msg.info.origin
            np = self.tf.transformPose('/map', p)
            msg.header = np.header
            msg.info.origin = np.pose

        self.other_data.append( (rospy.Time.now(), topic, msg) )

    def goto(self, loc, debug=False):
        if self.ac is None:
            return []
        self.goal = loc
        q = quaternion_from_euler(0, 0, loc[2])
        goal = MoveBaseGoal()
        goal.target_pose.header.frame_id = self.base_frame
        goal.target_pose.header.stamp = rospy.Time.now()
        goal.target_pose.pose.position.x = loc[0]
        goal.target_pose.pose.position.y = loc[1]
        goal.target_pose.pose.orientation.w = q[3]
        goal.target_pose.pose.orientation.x = q[0]
        goal.target_pose.pose.orientation.y = q[1]
        goal.target_pose.pose.orientation.z = q[2]

        rate = rospy.Rate(self.record_rate)
        self.data = []
        self.other_data = []
        self.recording = True

        self.subscribers = []

        for topic, msg_type in self.subscriptions:
            sub = rospy.Subscriber(topic, msg_type, self.cb, topic)
            self.subscribers.append(sub)

        rospy.sleep(0.5)
        self.ac.send_goal(goal)

        if debug:
            timer = rospy.Timer(rospy.Duration(5), self.print_distance)

        start_time = rospy.Time.now()

        while not finished(self.ac.get_state()) and rospy.Time.now() < start_time + self.timeout:
            t, pose = get_time_and_pose(self.tf, self.base_frame, self.target_frame)
            if pose is not None:
                self.data.append((t,"/robot_pose", pose))
            else:
                print 'TF Error'
            rate.sleep()

        if debug:
            timer.shutdown()

        self.recording = False
        rospy.sleep(1)

        for sub in self.subscribers:
            sub.unregister()

        # save footprint
        footprint_param = rospy.get_param('/move_base_node/footprint', [])
        footprint = Polygon()
        if type(footprint_param)==type([]):
            for x,y in footprint_param:
                footprint.points.append( Point32(x,y,0.0) )
        else: #string
            for subs in footprint_param[2:-2].split('],['):
                x,y = subs.split(',')
                footprint.points.append( Point32(float(x),float(y),0.0))

        self.other_data.append( (t, '/footprint', footprint) )

        # save the rest of the configuration
        params = rospy.get_param('/')
        params_str = std_msgs.msg.String()
        params_str.data = yaml.dump(params, default_flow_style=False)
        self.other_data.append( (t, '/parameters', params_str) )

        return self.data + self.other_data

    def print_distance(self, event=None):
        if len(self.data)==0:
            return
        pose = self.data[-1][2]
        dx = abs(self.goal[0]-pose.x)
        dy = abs(self.goal[1]-pose.y)
        dt = abs(self.goal[2]-pose.theta)
        rospy.loginfo( "dx: %.2f dy: %.2f dt: %d"%(dx, dy, int(dt*180/3.141)) )

    def load_subscriptions(self):
        #TODO: Load classes dynamically
        topics = rospy.get_param('/nav_experiments/topics', [])
        for topic in topics:
            if 'plan' in topic:
                self.addSubscription(topic, Path)
            elif 'command' in topic or 'cmd_vel' in topic:
                self.addSubscription(topic, Twist)
            elif 'costmap_updates' in topic:
                self.addSubscription(topic, OccupancyGridUpdate)
            elif 'costmap/costmap' in topic:
                self.addSubscription(topic, OccupancyGrid)
            elif 'cloud' in topic:
                self.addSubscription(topic, PointCloud2)
            else:
                rospy.logerr("unknown type for %s"%topic)
        self.addSubscription('/collisions', std_msgs.msg.String)
        self.addSubscription('/simulation_state', ModelStates)
        self.addSubscription('/move_base_node/global_costmap/update_time', std_msgs.msg.Float32)
        self.addSubscription('/move_base_node/local_costmap/update_time', std_msgs.msg.Float32)
        self.addSubscription('/people', people_msgs.msg.People)
    #    mb.addSubscription('/move_base_node/global_costmap/cycle_times', CycleTimes)
    #    mb.addSubscription('/move_base_node/local_costmap/cycle_times', CycleTimes)
    #    mb.addSubscription('/move_base_node/global_costmap/cycle_times_G', CycleTimesG)    
    #    mb.addSubscription('/move_base_node/local_costmap/cycle_times_G', CycleTimesG)


