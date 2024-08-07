import numpy as np
import heapq
import math
import pygame
from copy import deepcopy

#=============================================
# 프로그램에서 사용할 변수, 저장공간 선언부
#============================================= 
rx, ry = [300, 350, 400, 450], [300, 350, 400, 450]

#=============================================
# 프로그램에서 사용할 상수 선언부
#=============================================
AR = (1142, 62) # AR 태그의 위치
P_ENTRY = (1036, 162) # 주차라인 진입 시점의 좌표
P_END = (1129, 69) # 주차라인 끝의 좌표

#=============================================
# 경로를 생성하는 함수
# 차량의 시작위치 sx, sy, 시작각도 syaw
# 최대가속도 max_acceleration, 단위시간 dt 를 전달받고
# 경로를 리스트를 생성하여 반환한다.
#=============================================
def planning(sx, sy, syaw, max_acceleration, dt):
    global rx, ry
    global reverse_end_index    # 전진경로와 후진경로를 나누는 경계 인덱스 변수수
    print("Start Planning")

    '''
    1. 주차 각도 계산
    2. 경로 최종 위치 계산
    3. 주차장 꼭지점을 계산
    4. 맵 축소(계산량 줄이기, 하지만 정확도가 떨어질 수 있다는 문제 발생)
    5. A* 알고리즘 실행 (시작이 전진, 후진 두 경우)
    6. 두 경로 중 더 짧은 것을 선택
    7. 경로를 원래 맵 크기로 복원
    8. 샘플링을 통해 Path Smoothing
    9. 샘플링에 의해 노드가 서로 멀리 떨어져있으므로 중간 채우기
    10. 경로 반환
    '''
    
    reduce_rate = 4 #MAP 축소 비율 -> Path Planning 시간 단축

    #화면은 1200*800이다.
    border = (((0,0), (1200//reduce_rate,0)), ((1200//reduce_rate,0), (1200//reduce_rate, 800//reduce_rate)),
                ((1200//reduce_rate, 800//reduce_rate), (0, 800//reduce_rate)), ((0, 800//reduce_rate), (0, 0)))
    
    goal_angle = math.atan2(P_END[1]-P_ENTRY[1], P_END[0]-P_ENTRY[0]) #주차 각도
    goal_center = (P_ENTRY[0]*0.3+P_END[0]*0.7, P_ENTRY[1]*0.3+P_END[1]+0.7) #주차 중심
    goal_center_reduced = (goal_center[0]//reduce_rate, goal_center[1]//reduce_rate) #축소된 MAP에서의 주차 중심

    astar = AStar([50//reduce_rate, 85//reduce_rate], border, 50, 55) #A* 알고리즘 객체 생성
    path_0 = astar.run((int(sx//reduce_rate), int(sy//reduce_rate)), goal_center_reduced, syaw, goal_angle, 'drive') #알고리즘 실행(전진)
    path_1 = astar.run((int(sx//reduce_rate), int(sy//reduce_rate)), goal_center_reduced, syaw, goal_angle, 'reverse') #알고리즘 실행(전진)
    
    #더 짧은 경로 선택
    if len(path_0) == 0:
        path_ = path_1
    elif len(path_1) == 0:
        path_ = path_0
    elif len(path_0) <= len(path_1):
        path_ = path_0
    else:
        path_ = path_1
    #path_ = path_1

    path_ = list(zip([(p[0]+0)*reduce_rate for p in path_], [(p[1]+0)*reduce_rate for p in path_])) #원래 맵 크기로 복원

    path_ = [[x,y] for x,y in path_][::max(len(path_)//20, 1)] #Sampling
    path_ = astar.smooth(path_, 0.1, 0.2) #Smoothing


    path_final = [] #fill in path
    for i in range(len(path_)-1):
        path_final.extend(zip(np.linspace(path_[i][0], path_[i+1][0], 10+1),
                np.linspace(path_[i][1], path_[i+1][1], 10+1)))
    path_final.append(path_[-1])

    rx = [x[0] for x in path_final]
    ry = [x[1] for x in path_final]

    # 주행 경로에서 후진을 완료한 후 전진을 시작하는 지점의 인덱스를 찾기
    #reverse_end_index = find_reverse_end_index(rx, ry)  # 전진과 후진을 구분짓는 인덱스 반환
    # 인덱스 단위 벡터를 만들어서 내적한 후 나온 값으로 전진/후진 경로가 있는 경우 경계 인덱스 찾는 함수

    print("Finished Planning")

    return rx, ry

# -----------------------
def Transformation_Matrix(degree, org): #Z축 Rotation, Translation Matrix
    #좌표계 변환용 
    T = np.array([[math.cos(degree), -math.sin(degree), 0, org[0]],
                [math.sin(degree), math.cos(degree), 0, org[1]],
                [0, 0, 1, 0],
                [0, 0, 0, 1]])
    
    return T
# -----------------------

class Queue(object):
    def __init__(self):
        self.elements = []

    def length(self):
        return len(self.elements)

    def push(self, x, priority):
        heapq.heappush(self.elements, (priority, x))

    def pop(self):
        return heapq.heappop(self.elements)[1]


class AStar():
    def __init__(self, barrier, border, collision_gain, theta_gain):
        '''
        collision_gain: 현재 노드에서 목표 노드까지 직선으로 이었을 때, 장애물이 존재하면 부여하는 이득
        theta_gain: (현재 노드에서 목표 노드까지의 각도)와 (목표 각도)의 차에 부여하는 이득
        '''
        self.queue = None
        self.came_from = None
        self.cost_so_far = None
        self.barrier_w = barrier[0]
        self.barrier_h = barrier[1]
        self.theta = None
        self.collision_gain = collision_gain
        self.theta_gain = theta_gain
        self.border = border

    def run(self, start, goal, start_theta, goal_theta, gear):
        self.queue = Queue()
        #self.queue.push(start, 0)
        self.came_from = {}
        self.cost_so_far = {}
        self.cost_so_far[start] = 0
        self.start_theta = start_theta #자동차 시작 각도
        self.goal_theta = goal_theta   #목표 주차 각도

        self.gear = gear #'drive':전진, 'reverse':후진

        self.barrier_transformation_matrix = np.linalg.inv(np.array([[math.cos(-goal_theta),-math.sin(-goal_theta),0,goal[0]],[math.sin(-goal_theta),math.cos(-goal_theta),0,goal[1]],[0,0,1,0],[0,0,0,1]]))

        #------- 후보 노드 선정 --------
        '''
        자동차는 제자리에서 회전할 수 없으며, 앞 뒤로 움직이면서 회전하기 때문에 바로 옆으로 이동하는 등의 모션을 보일 수 없다.
        즉, A노드에서 B노드로 이동할 때 B는 A의 방향에 귀속된다.

        노드 A의 방향은 A의 직전노드와 A노드의 벡터의 방향으로 표현된다.
        
        자동차 좌표계에서 자동차는 x축과 평형, y축과 수직이며 원점에 위치한다.
        자동차 좌표계에서 원점에서 next_radius만큼의 반지름을 갖는 원을 가질 때, 원 위의 점들 중 x축으로부터 특정 각도에 위치하는 노드로만 이동할 수 있다.

        x = +-sqrt(y^2 - r^2)으로 계산된다. 차가 전진 중이라면 x는 양수, 후진 중이라면 x는 음수를 갖는다.
        y에 값을 넣으면 x가 계산된다. y는 반지름을 next_div로 나눈 값을 a라고 할 때 -a ~ a까지의 범위를 갖는다.
        예를 들어, next_radius=12, next_div=4라면 y는 -3 ~ 3까지의 범위를 갖는다.

        이 범위 내에서 고르게 sampling을 하기 위해 numpy.linespace를 이용했으며, 현재는 5개의 점을 sampling을 한다.

        여기서 계산된 (x, y)는 현재 노드에서 다음 노드로 이동할 수 있는 후보이다. 이를 next_keys에 저장한다.
        
        '''
        next_radius, next_div = 10, 4
        next_keys = []
        for i in np.linspace(-next_radius/next_div, next_radius/next_div, 5+1):
            next_keys.append((math.sqrt(next_radius**2 - i**2), i, 0, 1)) #다음 경로 후보
        #--------------------------------------

        #------- 경로 시작 위치 지정 -----------
        '''
        자동차가 이동할 때 기준이 되는 점은 차 중심이 아니라 범퍼 쪽, 혹은 트렁크 쪽일 것이다.
        따라서, 자동차가 따라가야 하는 경로의 시작점은 차의 중심이 되어서는 안 된다.

        이 부분은 경로가 시작점을 정하는 과정이다. 전진이라면 10만큼 앞에, 후진이라면 10만큼 뒤에 둔다.
        '''
        T01 = Transformation_Matrix((np.pi/2 + start_theta*np.pi/180), [start[0], start[1]]) #{자동차 좌표계}->{기준 좌표계}
        if self.gear == 'drive': #전진이라면
            start_point = np.transpose(np.dot(T01, np.transpose([10, 0, 0, 1]))) #앞으로 10만큼
        elif self.gear == 'reverse': #후진이라면
            start_point = np.transpose(np.dot(T01, np.transpose([-10, 0, 0, 1]))) #뒤로 10만큼
        start_point = (int(start_point[0]), int(start_point[1]))
        #--------------------------------------

        #------ 경로 생성 시작 --------
        '''
        A* 알고리즘을 기반으로 한다.
        휴리스틱 추정치로는 총 3가지를 사용한다:
            1. 후보 노드로부터 목표 노드까지의 직선 거리
                -> 목표와 빠르게 접근
            2. 후보 노드로부터 목표노드까지 직선으로 이었을 때 주차장을 둘러싸는 가상의 장애물 존재 여부
                -> 장애물이 존재한다면 현재 방향으로 가면 마지막에 틀어져서 주차될 가능성이 높음
            3. 후보 노드로부터 목표노드까지의 각도와, 목표 주차 각도의 차이
                -> 이동 방향이 목표 주차 방향과 일치하도록 함

        후보 노드는 부모 노드가 있는데, 이는 came_from이라는 dictionary 객체에 저장된다.
        
        후보 노드가 정확하에 목표 지점 위에 도달 안 할 수도 있기 때문에 특정 범위 안에 있다면 도착한 것으로 인정한다.

        자동차가 후진 및 전진을 할 수 있으므로, 이를 구분하여 준다.
        맵 특성상 경로는 {전진}, {후진, 전진}으로 이루어진다.
        {후진, 전진}의 경우 후진에서 전진으로 변환할 수 있는 노드에 도착했을 시에, turn_flag를 True 설정한다.
        turn_flag가 True라면 해당 노드로부터 목표 노드까지 경로를 생성한다.
        '''

        self.came_from[start_point] = start #위에서 선정한 시작점의 이전 노드를 차의 중심으로 설정
        self.cost_so_far[start_point] = 0
        self.queue.push(start_point, 0)

        end_pos = None #도착 노드
        turn_flag = False #후진 -> 전진 Flag

        #경로 생성 시작
        while self.queue.length() > 0:
            current = self.queue.pop()

            if (current[0]-goal[0])**2 + (current[1]-goal[1])**2 <= 5**2 * 0.5: #도착지점과 정확히 일치 안 할 수도 있으므로
                end_pos = current
                break

            (x, y) = current                    #현재 노드
            (xb, yb) = self.came_from[current]  #부모 노드

            if self.gear == 'reverse': #현재 경로가 후진 경로라면
                cr2d, ang = self.check_reverse2drive(current, self.came_from[current], goal) #후진->전진으로 전환할 수 있는 노드인지 판별
                if cr2d: #만약 변환할 수 있다면
                    end_pos = current
                    turn_flag = True
                    break #알고리즘 종료

            degree_ = math.atan2(y-yb, x-xb)                            #부모 노드와 현재 노드까지 각도
            T01 = Transformation_Matrix(degree_, [x, y])                #{자동차 좌표계}->{기준 좌표계}
            candi = np.transpose(np.dot(T01, np.transpose(next_keys)))  #다음 이동 가능한 후보 노드 계산
            candidates = [(int(p[0]), int(p[1])) for p in candi]        #다음 이동 가능한 후보 노드 계산

            for next in [(h, v) for h, v in candidates]: #후보 노드 중에서
                new_cost = self.calc_cost(current, next) #비용 계산

                #cost가 낮고, 화면을 벗어나는 경로 및 주차 장애물을 가로지는 것이 아니라면
                if (next not in self.came_from or new_cost < self.cost_so_far[next]) and (self.check_border(current, next) == 0) and (self.check_barrier(current, next) == 0):
                    self.queue.push(next, new_cost + self.heuristic(goal, next, current, self.came_from[current]))
                    self.cost_so_far[next] = new_cost
                    self.came_from[next] = current

        #---------------------------------

        #-------- 경로 백트래킹 과정 ---------
        current = end_pos
        path = []
        if current is not None:
            while current is not start:
                path.append(current)
                current = self.came_from[current]
            path.reverse()
        #------------------------------------

        #만약 후진->전진으로 변환하는 경로였다면,
        if turn_flag:
            #목표 지점을 바라본 상태로 전진 경로 생성
            path.extend(self.run(end_pos, goal, goal_theta-90, goal_theta, 'drive'))

        #완성된 경로 반환
        return path

    #----- 비용 계산 함수 ------
    '''
    하나의 노드에서 다른 노드까지 이동할 때 비용을 1이라 상정.
    '''
    def calc_cost(self, current, next):
        (x, y) = next
        return self.cost_so_far[current] + 1
    #--------------------------

    #----- 휴리스틱 계산 함수 -------
    def heuristic(self, goal, next, current, before):
        '''
        전진이라면 목표와 가까워지는 것이 좋고, 후진이라면 목표랑 멀어져서 전진으로 전환할 수 있는 노드를 찾는 것이 좋다.
        즉, 전진이라면 직선 거리를 더하고, 후진이라면 직선 거리를 뺀다.
        '''
        #Shortest Distance + Collision + Degree Difference를 휴리스틱값
        if self.gear == 'drive':
            dst_gain = 1
        else:
            dst_gain = -1

        return self.check_dist(goal, next) * dst_gain + self.check_collision(goal, next) + self.check_degree(goal, next)
    #--------------


    #------- 후진에서 전진으로 전환 가능한 노드인지 판단하는 함수 ----------
    '''
    u = 현재 노드 -> 부모 노드 벡터
    v = 현재 노드 -> 목표 노드 벡터

    u, v 벡터 사이의 각도를 구해서 사이각이 threshold보다 작으면 멈추고, 전진이 가능하다고 판단.
    '''
    def check_reverse2drive(self, current, before, goal):

        u = [before[0]-current[0], before[1]-current[1]]
        v = [goal[0]-current[0], goal[1]-current[1]]
        angle = self.angle_between(u, v) #벡터 사이 각도 계산

        #threshold = np.pi/9
        if angle <= np.pi/9:
            return True, angle
        else:
            return False, angle

    #-------------------------------------------------------------------

    #------- 벡터 계산 수단 ---------
    '''
    이건 구글링이라..... 그렇대요.....
    '''
    def unit_vector(self, vector):
        """ Returns the unit vector of the vector.  """
        return vector / np.linalg.norm(vector)

    def angle_between(self, v1, v2):
        """ Returns the angle in radians between vectors 'v1' and 'v2'::

                >>> angle_between((1, 0, 0), (0, 1, 0))
                1.5707963267948966
                >>> angle_between((1, 0, 0), (1, 0, 0))
                0.0
                >>> angle_between((1, 0, 0), (-1, 0, 0))
                3.141592653589793
        """
        v1_u = self.unit_vector(v1)
        v2_u = self.unit_vector(v2)
        return np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0))
    #--------------------------------
    
    #------- 휴리스틱 값 중 후보 노드로부터 목표 노드까지의 직선 거리 계산 함수 --------
    def check_dist(self, goal, next):
        (x1, y1) = goal
        (x2, y2) = next

        dx = x1 - x2
        dy = y1 - y2
        
        return math.sqrt(dx*dx+dy*dy) #다음 노드부터 목표 노드까지의 직선 거리 반환
    #------------------------------------------------------------------------------

    #------- 휴리스틱 값 중 후보 노드로부터 목표 노드까지 직선 거리에 장애물이 있는지 판단하는 함수 ------
    def check_collision(self, goal, next): #주차장 주위 가상 장애물과 현재 위치에서 주차장까지 직선 거리가 교차하는지
        
        if next == goal:
            return 0 #다음 노드와 목표 노드가 동일하므로 0 반환
        
        #for bi in self.barrier_list:
        #    if self.line_intersect(next, goal, bi[0], bi[1]) is not None:
        #        return self.collision_gain #장애물이 존재하므로 gain 반환

        p = np.transpose(np.dot(self.barrier_transformation_matrix, np.transpose([next[0], next[1], 0, 1])))[1]
        
        if abs(p) >= self.barrier_w:
            return self.collision_gain

        return 0 #다음 노드부터 목표 노드까지 아무런 장애물이 없으므로 0 반환
    #-----------------------------------------------------------------------------------------------

    #------- 휴리스틱 값 중 후보노드로부터 목표노드까지의 각도와, 목표 주차 각도의 차이 함수 -------
    def check_degree(self, goal, next):
        
        u = np.array(goal) - np.array(next) #다음 노드부터 목표 노드까지의 벡터
        u_theta = math.atan2(u[1], u[0])    #벡터의 각도 계산
        
        dt = abs(abs(u_theta) - abs(self.goal_theta))*self.theta_gain #목표 각도와, u 벡터의 각도 차 계산, 그 후 theta_gain 곱하기
        
        return int(dt)
    #------------------------------------------------------------------------------------------

    #----- 두 직선 교차하는지 판단하는 함수 --------
    '''
    구글링한 건데... 뭔가 이상한 듯한 느낌....? 좌표계가 뒤집혀있어서 그런가...
    '''
    def line_intersect(self, p1, p2, p3, p4): #두 직선이 교차하는지 판단하는 함수
        x1,y1 = p1
        x2,y2 = p2
        x3,y3 = p3
        x4,y4 = p4
        denom = (y4-y3)*(x2-x1) - (x4-x3)*(y2-y1)
        if denom == 0: # parallel
            return None
        ua = ((x4-x3)*(y1-y3) - (y4-y3)*(x1-x3)) / denom
        if ua < 0 or ua > 1: # out of range
            return None
        ub = ((x2-x1)*(y1-y3) - (y2-y1)*(x1-x3)) / denom
        if ub < 0 or ub > 1: # out of range
            return None
        x = x1 + ua * (x2-x1)
        y = y1 + ua * (y2-y1)
        return (x,y)
    #---------------------------------------------
    
    
    #------ 노드가 화면 밖인지 판단하는 함수 -------
    def check_border(self, current, next):
        if next == current:
            return 0 #다음 노드와 목표 노드가 동일하므로 0 반환

        if next[0] < self.border[0][0][0] or next[0] > self.border[2][0][0]:
            return 1
        if next[1] < self.border[0][0][0] or next[1] > self.border[2][0][1]:
            return 1

        return 0 #다음 노드부터 목표 노드까지 아무런 장애물이 없으므로 0 반환
    #---------------------------------------------
    
    #------ 노드가 주차장 경계를 지나가는지 판단하는 함수 -------
    def check_barrier(self, current, next):
        if next == current:
            return 0 #다음 노드와 목표 노드가 동일하므로 0 반환

        n = np.transpose(np.dot(self.barrier_transformation_matrix, np.transpose([next[0], next[1], 0, 1])))
        c = np.transpose(np.dot(self.barrier_transformation_matrix, np.transpose([current[0], current[1], 0, 1])))
        
        #print(p1, p2)
        ##print(self.barrier_h, self.barrier_w)

        #if abs(p2[0])>=self.barrier_h and abs(p1[0]<=self.barrier_h):
        #    print("yey")

        if(abs(n[1]) <= self.barrier_h):
            
            if abs(c[0]) > self.barrier_w and abs(n[0]) < self.barrier_w:
                #print(p1[:2], p2[:2], self.barrier_w)
                return 1

        return 0 #다음 노드부터 목표 노드까지 아무런 장애물이 없으므로 0 반환
    #---------------------------------------------
    
    #이건 뭐지
    def objective(self, x, a, b, c, d):
         return a * sin(b - x) + c * x**2 + d
    
    #------ 경로를 부드럽게하는 함수 ---------
    '''
    구글링이라 몰라요 ㅎㅎ
    '''
    def smooth(self, path, weight_data=0.5, weight_smooth=0.1, tolerance=0.000001): #Smoothing Algorithm
        
        new = deepcopy(path)
        dims = len(path[0])
        change = tolerance

        while change >= tolerance:
            change = 0.0
            for i in range(1, len(new) - 1):
                for j in range(dims):

                    x_i = path[i][j]
                    y_i, y_prev, y_next = new[i][j], new[i - 1][j], new[i + 1][j]

                    y_i_saved = y_i
                    y_i += weight_data * (x_i - y_i) + weight_smooth * (y_next + y_prev - (2 * y_i))
                    new[i][j] = y_i

                    change += abs(y_i - y_i_saved)

        return np.array(new, dtype='int').tolist()
    #----------------------------------------   
    
#------ 주차장 주변에 가상의 장애물 생성하는 함수 --------
'''
주차장 공간 옆에서 들어가는 일 방지, 즉 목표 주차 각도로만 진입하게 된다.

ㅁㅁㅁㅁㅁㅁㅁㅁ
ㅁ           ㅁ
ㅁ     주    ㅁ
ㅁ     차    ㅁ
ㅁ     공    ㅁ
ㅁ     간    ㅁ
ㅁ           ㅁ

이거 안 써용
'''
def create_imaginary_boundary(parking_theta, parking_xy, width, height, ar):
    T01 = Transformation_Matrix(-parking_theta, parking_xy) #Transformation Matrix 정의 Z축 회전 {0}: 기준 좌표계, {1}: 주차 공간 좌표계
    T10 = np.linalg.inv(T01) #역함수
    finish_point = np.dot(T10, np.transpose([ar[0], ar[1], 0, 1]))[0:2]

    x_idxs = range(-height//2, int(finish_point[0]))
    y_idxs = range(-width//2, width//2)

    #{주차 공간 좌표계}에서 주차 공간 근처에 가상 장애물 정의
    parking_barrier1 = np.concatenate(([[x,y, 0, 1] for (x,y) in zip(list(x_idxs), [width//2 for _ in x_idxs])],
                                      [[x,y, 0, 1] for (x,y) in zip([finish_point[0] for _ in y_idxs], list(y_idxs))],
                                      [[x,y, 0, 1] for (x,y) in zip(list(x_idxs), [-width//2 for _ in x_idxs])]))
    parking_barrier1 = np.transpose(parking_barrier1)
    parking_barrier0 = np.dot(T01, parking_barrier1) #{주차 공간 좌표계} -> {기준 좌표계}로 좌표 변환
    barriers = [(p[0],p[1]) for p in np.transpose(parking_barrier0)]
    barriers = np.array(barriers, dtype='int') #{기준 좌표계}에서 index를 위해 interpolation이 아닌 단순 truncate
    
    return barriers
#-------------------------------------------------------

#------- 주차공간 꼭지점 계산하는 함수 --------
'''
주차장 공간 옆에서 들어가는 일 방지, 즉 목표 주차 각도로만 진입하게 된다.

ㅁㅁㅁㅁㅁㅁㅁㅁ
ㅁ           ㅁ
ㅁ     주    ㅁ
ㅁ     차    ㅁ
ㅁ     공    ㅁ
ㅁ     간    ㅁ
ㅁ           ㅁ
'''
def create_parking_lines(parking_theta, parking_xy, width, height):
    T01 = np.array([[math.cos(-parking_theta), -math.sin(-parking_theta), 0, parking_xy[0]],
                [math.sin(-parking_theta), math.cos(-parking_theta), 0, parking_xy[1]],
                [0, 0, 1, 0],
                [0, 0, 0, 1]]) #{기준 좌표계}에서 {주차 공간 좌표계}로 변환하는 Transformation Matrix 생성
    
    #주차 공간 꼭지점
    parking_v1 = np.array([[-height//2, width//2, 0, 1],[height//2, width//2, 0, 1],
                           [height//2, -width//2, 0, 1],[-height//2, -width//2, 0, 1]])
    
    parking_v1 = np.transpose(parking_v1)
    parking_v0 = np.dot(T01, parking_v1) #{주차 공간 좌표계} -> {기준 좌표계}로 좌표 변환
    parking_v = [(p[0],p[1]) for p in np.transpose(parking_v0)]
    pv = np.array(parking_v, dtype='int') #{기준 좌표계}에서 index를 위해 interpolation이 아닌 단순 truncate
    
    parking_v = ((pv[0], pv[1]),(pv[1], pv[2]),(pv[2], pv[3]),(pv[3], pv[0]))
    
    return [parking_v[0], parking_v[2]]
#--------------------------------------------