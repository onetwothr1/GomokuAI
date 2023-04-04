import copy
from collections import namedtuple
from renju_rule import Renju_Rule
from player import Player

class Point(namedtuple('Point', 'row col')):
    def __init__(self, row, col):
        pass

class NoPossibleMove():
    def __init__(self):
        pass

class Board():
    def __init__(self, board_size):
        self.board_size = board_size
        self.grid = []
        self.init_grid()

    def init_grid(self):
        for r in range(self.board_size):
            row = []
            for c in range(self.board_size):
                row.append(0)
            self.grid.append(row)

    def is_empty(self, point):
        return self.grid[point.row][point.col]==0

    def get(self, point):
        return self.grid[point.row][point.col]
    
    def place_stone(self, player, point):
        self.grid[point.row][point.col] = player

    def is_on_grid(self, point):
        return 0 <= point.row < self.board_size and 0 <= point.col < self.board_size

    def is_full(self):
        for row in self.grid:
            for point in row:
                if point == 0:
                    return False
        return True
    

class GameState():
    def __init__(self, board, next_player, previous, move):
        self.board = board
        self.next_player = next_player
        self.previous_state = previous
        self.last_move = move
        self.rule = Renju_Rule(self.board)
        self.win_by_forcing_forbidden_move = False

    def apply_move(self, move):
        import utils
        if isinstance(move, NoPossibleMove):
            self.win_by_forcing_forbidden_move = True
            self.winner = self.prev_player()
            return self
        # print('before board')
        # utils.print_board(self.board)
        next_board = copy.deepcopy(self.board)
        # print('after copy')
        # utils.print_board(next_board)

        next_board.place_stone(self.next_player, move)
        # print('after place stone')
        # utils.print_board(next_board)

        return GameState(next_board, self.next_player.other, self, move)

    # one-man play. for checking applied rules.
    def apply_move_test(self, move):
        next_board = copy.deepcopy(self.board)
        next_board.place_stone(self.next_player, move)
        return GameState(next_board, self.next_player, self, move)

    def new_game(board_size: int):
        board = Board(board_size)
        return GameState(board, Player.black, None, None)

    def is_empty(self, move):
        return self.board.is_empty(move)
    
    def is_valid_move(self, move):
        if self.next_player == Player.black:
            if self.rule.forbidden_point(move.col, move.row, Player.black):
                return False
        return True

    def legal_moves(self):
        moves = []
        for row in range(0, self.board.board_size):
            for col in range(0, self.board.board_size):
                move = Point(row, col)
                if not self.is_empty(move):
                    continue
                if self.is_valid_move(move):
                    moves.append(move)
        return moves
    
    def forbidden_moves(self):
        if self.next_player == Player.white:
            return []
        
        _forbidden_moves = []
        for row in range(0, self.board.board_size):
            for col in range(0, self.board.board_size):
                if not self.board.is_empty(Point(row, col)):
                    continue
                if self.rule.forbidden_point(col, row, Player.black):
                    _forbidden_moves.append(Point(row=row, col=col))
        return _forbidden_moves

    def is_over(self):
        if self.previous_state is None:
            return False
        if self.board.is_full():
            self.winner = None
            return True
        if self.win_by_forcing_forbidden_move:
            return True
        if self.check_five():
            self.winner = self.prev_player()
            return True

    def check_five(self):
        return self.rule.is_five(self.last_move.col, self.last_move.row, self.prev_player())
    
    def prev_player(self):
        if self.previous_state is None:
            return None
        return self.previous_state.next_player