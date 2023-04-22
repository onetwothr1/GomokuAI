import torch
import numpy as np
from tqdm import tqdm
import random
from agent import Agent
from board import NoPossibleMove
from utils import coords_from_point, visualize_policy_distibution

class Branch:
    def __init__(self, prior):
        self.prior = prior # prior probability from policy net
        self.initial_value = None # expected value from value net. 
                                  # we can get this value after branching the node.
        self.visit_count = 0
        self.total_value = 0.0
        self.loss_predicted = 0

class AlphaZeroTreeNode:
    def __init__(self, state, value, priors, parent, last_move):
        self.state = state
        self.value = value
        self.parent = parent
        self.priors = priors
        self.last_move = last_move
        self.total_visit_count = 1
        self.branches = {}

        for move, p in priors.items():
            if state.is_empty(move) and state.is_valid_move(move):
                self.branches[move] = Branch(p)
        self.children = {} 

    def moves(self):
        return self.branches.keys()

    def add_child(self, move, child_node, value):
        self.children[move] = child_node
        self.branches[move].initial_value = value

    def has_child(self, move):
        return move in self.children

    def get_child(self, move):
        return self.children[move]  

    def expected_value(self, move):
        branch = self.branches[move]
        if branch.visit_count == 0:
            return 0.0
        return branch.total_value / branch.visit_count
    
    def prior(self, move):
        return self.branches[move].prior
    
    def initial_value(self, move):
        return self.branches[move].initial_value

    def total_value(self, move):
        return self.branches[move].total_value
    
    def increase_loss_predicted(self, move):
        self.branches[move].loss_predicted += 1

    def loss_predicted(self, move):
        return self.branches[move].loss_predicted
    
    def visit_count(self, move):
        if move in self.branches:
            return self.branches[move].visit_count
        return 0
    
    def record_visit(self, move, value):
        self.total_visit_count += 1
        self.branches[move].visit_count += 1
        self.branches[move].total_value += value

class AlphaZeroAgent(Agent):
    def __init__(self, model, encoder, rounds_per_move=1000, c=2.0, 
                 is_self_play=False, dirichlet_noise_intensity=0.25, 
                 dirichlet_alpha=0.05, verbose=0, name=None):
        self.model = model
        self.encoder = encoder
        self.num_rounds = rounds_per_move
        self.c = c
        self.is_self_play = is_self_play
        self.noise_intensity = dirichlet_noise_intensity
        self.alpha = dirichlet_alpha
        self.verbose = verbose # 0: none, 1: progress bar, 2: + thee-depth 3: + candidate moves
        self.name = name
        self.reward_decay = 0.95
        self.collector = None # used when generating self-play data
        self.avg_depth_list = [] # average of tree-depth in MCTS
        self.max_depth_list = [] # max tree-depth per each move
    
    def select_move(self, game_state):
        # Tree Search
        root = self.create_node(game_state)
        depth_cnt_list = []
        search_cnt = 0
        additional_search = 0
        original_c = self.c

        while True:
            # Walking down the tree
            depth_cnt = 1
            node = root
            next_move = self.select_branch(node)
            root_child_move = next_move
            while node.has_child(next_move):
                node = node.get_child(next_move)
                next_move = self.select_branch(node)
                depth_cnt += 1
            depth_cnt_list.append(depth_cnt)

            if next_move is not None:
                # Expanding the tree
                new_state = node.state.apply_move(next_move)
                if new_state.check_winning(): # win
                    value = 1 # winner gets explicit reward from game result
                elif new_state.board.is_full(): #draw
                    value = 0 # get explicit reward from game result
                else:
                    child_node = self.create_node(
                        new_state, last_move=next_move, parent=node)
                    value = -1 * child_node.value
                move = next_move
            else: 
                # no possible move available except forbidden moves. current player lost.
                value = 1 # winner gets explicit reward from game result
                move = node.last_move
                node = node.parent # winner

            # Back up
            while node is not None:
                node.record_visit(move, value)
                move = node.last_move
                node = node.parent
                if value==1 and new_state.prev_player()==game_state.next_player.other:
                    # when enemy wins, decrease the impact of reward decay to make the agent focus more on defense.
                    reward_decay = 0.99
                    root.increase_loss_predicted(root_child_move)
                else:
                    reward_decay = self.reward_decay
                value = -1 * reward_decay * value

            # end tree searching
            search_cnt += 1
            if search_cnt == self.num_rounds:
                # if most visited move and second's visit count are closs, try more search
                if len(root.moves()) < 2:
                    break
                if game_state.turn_cnt <= 8:
                    break
                if additional_search >= 4:
                    break
                sorted_moves = sorted(root.moves(), key=root.visit_count, reverse=True)
                most_visit_move = sorted_moves[0]
                second_visit_move = sorted_moves[1]
                if root.loss_predicted(most_visit_move) / root.visit_count(most_visit_move) > 0.3:
                    self.c /= 3
                    search_cnt -= 200
                    additional_search += 1
                    # 높은 확률로 패배 예상됨 영어로 뭐라하지
                    print("too many loss predicted. additional search")
                elif root.visit_count(most_visit_move) <= root.visit_count(second_visit_move) + 15:                
                    search_cnt -= 200
                    additional_search += 1
                    print('additional search')
                else:
                    self.c = original_c
                    break
        
        # Statistics on tree-depth
        avg_depth = sum(depth_cnt_list) / len(depth_cnt_list)
        max_depth = max(depth_cnt_list)
        self.avg_depth_list.append(avg_depth)
        self.max_depth_list.append(max_depth)
        if self.verbose >= 2:
            print('average depth: %.2f, max depth: %d' %(avg_depth, max_depth))

        # If only moves left are forbidden moves
        if len(root.moves()) == 0:
            return NoPossibleMove()
        
        # Record on experience collrector
        if self.collector is not None:
            # print("Record on experience")
            root_state_tensor = self.encoder.encode_board(game_state)
            visit_counts = np.array([
                root.visit_count(
                    self.encoder.decode_move_index(idx))
                for idx in range(self.encoder.num_moves())
            ])
            mcts_prob = visit_counts / np.sum(visit_counts)
            self.collector.record_decision(
                root_state_tensor, mcts_prob)

        # Select a move
        if self.verbose >= 3:
            # print candidate moves with there visit count and output of policy net and value net.
            # if a candidate move has never been visited, it can not show the move's value. 
            for candidate_move in sorted(root.moves(), key=root.visit_count, reverse=True)[:10]:
                print(coords_from_point(candidate_move),
                      '    visit %3d  p %.3f  v %s  exp_v %5.2f  loss %d'
                        %(root.visit_count(candidate_move), 
                          root.prior(candidate_move), 
                          '%5.2f'%(root.initial_value(candidate_move)) if root.initial_value(candidate_move) else '???',
                          root.expected_value(candidate_move),
                          root.loss_predicted(candidate_move)
                          )
                    )
        most_visit_move = max(root.moves(), key=root.visit_count)
        max_visit = root.visit_count(most_visit_move)
        max_tie_list = [move for move in root.moves() if root.visit_count(move)==max_visit]

        # visualize_policy_distibution(list(root.priors.values()), game_state)

        return random.choice(max_tie_list)

    def set_collector(self, collector):
        self.collector = collector

    def select_branch(self, node):
        if len(node.moves()) == 0:
            return None

        # exploration
        epsilon = 0.1
        if random.random() < epsilon:
            return random.choice(list(node.moves()))
        
        # exploitation
        total_n = node.total_visit_count

        def score_branch(move):
            q = node.expected_value(move)
            p = node.prior(move)
            n = node.visit_count(move)
            return q + self.c * p * np.sqrt(total_n) / (n + 1)
        
        return max(node.moves(), key=score_branch)

    def create_node(self, game_state, last_move=None, parent=None):
        state_tensor = self.encoder.encode_board(game_state)
        log_priors, values = self.model(state_tensor)
        priors = torch.exp(log_priors[0])
        value = values[0][0]    

        if self.is_self_play:
            # add Dirichlet noise for exploration
            priors = priors.detach().numpy()
            priors = ((1 - self.noise_intensity) * priors
                + self.noise_intensity * 
                np.random.dirichlet(self.alpha * np.ones(len(priors))))

        move_priors = {
            self.encoder.decode_move_index(idx): p
            for idx, p in enumerate(priors)
        }                                                      
        new_node = AlphaZeroTreeNode(
            game_state, value,
            move_priors,
            parent, last_move)
        if parent is not None:
            parent.add_child(last_move, new_node, value)
        return new_node