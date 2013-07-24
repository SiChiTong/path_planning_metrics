from path_planning_analysis.math_util import *

def time(path):
    """METRIC"""
    return (path.t[-1]-path.t[0]).to_sec()


def completed(path):
    """METRIC"""
    dist = path.get_distance_to_goal()
    angle = path.get_angle_to_goal()
    return 1.0 if dist < 0.2 and angle < .2 else 0.0

def translate_efficiency(path):
    """METRIC"""
    D = 0.0
    p0 = None
    for p in path.poses:
        if p0 is None:
            p0 = p
        D += dist(p,p0)
        p0 = p

    D0 = dist(path.poses[0], path.poses[-1])
    return inverse_scale(D-D0)
    
def rotate_efficiency(path):
    """METRIC"""
    p0 = None
    A = 0.0
    for pose in path.poses:
        if not p0:
            p0 = pose
        A += abs(a_dist(p0, pose))
        p0 = pose
    A0 = path.get_angle_to_goal()
    return inverse_scale(A-A0)

def face_direction_of_travel(path, mag_limit=0.1):
    """METRIC"""
    angles = [pose.theta for pose in path.poses]
    products = []
    for angle1, angle2, mag in zip(angles, path.headings, path.speeds):
        if mag > mag_limit:
            products.append( a_dist_helper(angle1, angle2) )
    m = average(products)
    return inverse_scale(m)

def curvature(path):
    """METRIC"""
    return average(path.curvatures)

def average_velocity_derivatives(path):
    """METRIC"""
    t = [x.to_sec() for x in path.t]
    results = {}
    results['average_velocity'] = average(path.speeds)
    a = derivative(t, path.speeds)
    results['average_acceleration'] = average(a)
    j = derivative(t, a)
    results['average_jerk'] = average(j)
    return results

def rotational_velocity_derivatives(path):
    """METRIC"""
    ts = []
    vels = []
    p0 = None
    
    for t, pose in zip(path.t, path.poses):
        if not p0:
            p0 = pose
            ts.append(0)
            vels.append(0.0)
        else:
            secs = t.to_sec()
            ts.append(secs)
            vels.append( a_dist(p0, pose)/secs )

    results = {}
    results['average_rotational_velocity'] = average(vels)
    a = derivative(ts, vels)
    results['average_rotational_acceleration'] = average(a)
    j = derivative(ts, a)
    results['average_rotational_jerk'] = average(j)
    
    return results

