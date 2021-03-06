import roslib; roslib.load_manifest('path_planning_ruler')
from path_planning_simulation import *
from path_planning_simulation.models import *
import rospy
import yaml
import os.path
import random

class GazeboObject:
    def __init__(self, name, m, params={}):
        self.name = name
        self.type = m.get('type', 'box')
        self.size = get_triple(m, 'size', [1,1,1], params)
        self.xyz = get_triple(m, 'xyz', [0,0,0], params)
        self.rpy = get_triple(m, 'rpy', [0,0,0], params)
        if 'movement' in m:
            self.movement =[]
            for frame in m['movement']:
                f = {}
                f['pos'] = get_triple(frame, 'pos', [0,0,0], params)
                f['t'] = eval_s(frame['t'], params)
                self.movement.append(f)
        else:
            self.movement = None
        self.is_person = m.get('class', '')=='person'
        self.spawn_name = None
        
    def get_spawn_name(self):
        if self.spawn_name is None:
            s = '%010x' % random.randrange(16**10)
            self.spawn_name = self.name + s
            
        return self.spawn_name
        
    def get_map(self):
        m = {'type': self.type, 'size': self.size, 'xyz': self.xyz, 'rpy': self.rpy}
        if self.movement:
            m['movement'] = self.movement
        if self.is_person:
            m['class'] = 'person'
        return m

    def get_xml(self):
        if self.type=='box':
            return box(self.get_spawn_name(), self.size, 
                        self.xyz, self.rpy, is_static=True)
        else:
            rospy.logerror("unknown type %s"%t)
            return None

class Scenario:
    def __init__(self, filename=None, the_dict=None):
        if filename is not None:
            self.key = os.path.splitext( os.path.basename(filename) )[0]
            self.scenario = yaml.load( open(filename) )
            self.vars = self.scenario.get('vars', {})
        else:
            self.key = the_dict['key']
            self.scenario = the_dict
            self.vars =[]
            self.parameterize()
    
    def parameterize(self, params={}):
        scenario = self.scenario
        
        if 'locations' in scenario:
            if 'start' not in scenario and 'start_i' in params:
                scenario['start'] = scenario['locations'][params['start_i']]
            if 'goal' not in scenario and 'goal_i' in params:
                scenario['goal'] = scenario['locations'][params['goal_i']]
        
        self.start = get_pose2d(scenario, 'start', params)
        self.goal = get_pose2d(scenario, 'goal', params)
        self.objects = {}
        for name, obj in scenario.get('objects', {}).iteritems():
            self.objects[name] = GazeboObject(name, obj, params)
        
        self.spawn_names = []

    def get_start(self):
        return self.start

    def get_goal(self):
        return self.goal

    def get_goal_triple(self):
        return (self.goal.x, self.goal.y, self.goal.theta)
        
    def get_timeout(self):
        return self.scenario.get('timeout', 90)

    def get_objects(self):
        return self.objects

    def spawn(self, gazebo ):
        self.spawn_names =[]
        sn_map = {}
        people_names = []
        for name, obj in self.objects.iteritems():
            xml = obj.get_xml()
            spawn_name = obj.get_spawn_name()
            sn_map[obj.name] = spawn_name
            self.spawn_names.append(spawn_name)
            if not xml:
                continue

            gazebo.spawn_model(spawn_name, xml, 
                                get_pose(obj.xyz[0], obj.xyz[1], obj.rpy[2]))
            
            if obj.is_person:
                people_names.append(spawn_name)
            if obj.movement:
                pos = obj.movement[0]['pos']
                gazebo.set_state(spawn_name, get_pose(pos[0], pos[1], pos[2]))
        rospy.set_param('/nav_experiments/people', people_names)
        rospy.set_param('/nav_experiments/spawn_names', sn_map)

    def unspawn(self, gazebo):
        for name in self.spawn_names:
            try:
                gazebo.delete_model(name)
            except rospy.service.ServiceException, e:
                rospy.logerr("Didn't delete model %s: %s" % (name, str(e)) )


    def reset(self, gazebo):
        rospy.sleep(1.0)
        gazebo.set_state('pr2', pose2d_to_pose(self.start))
        rospy.sleep(1.0)

    def get_endpoints(self, t=None):
        if t is None:
            t = rospy.Time.now()

        endpoints = []
        endpoints.append( (t, '/start', self.start) )
        endpoints.append( (t, '/goal' , self.goal ) )

        return endpoints
        
    def get_scenario(self):
        m = {'start': to_triple(self.start), 'goal': to_triple(self.goal)}
        o = {}
        for name, obj in self.objects.iteritems():
            o[name] = obj.get_map()
        if len(o)>0:
            m['objects'] = o
        return m
        
    def __repr__(self):
        return yaml.dump(self.get_scenario(), default_flow_style=False)

