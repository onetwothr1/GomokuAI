import agent
from player import Player
from board import GameState
from utils import *

def main():
    board_size = 9
    game = GameState.new_game(board_size)
    move = None
    print_board(game.board)
    bot = agent.RandomBot()

    while not game.is_over():
        clear_screen()
        print('----------------------------')
        print_move(game.prev_player(), move)
        print_board(game.board)

        if game.next_player == Player.black:
            human_input = input('-- ')
            move = handle_input(human_input, game, board_size)
            while move is None:
                human_input = input('-- ')
                move = handle_input(human_input, game, board_size)
        else:
            move = bot.select_move(game)
        game = game.apply_move(move)

    clear_screen()
    print('----------------------------')
    print_move(game.prev_player(), move)
    print_board(game.board)

    if game.winner:
        if game.win_by_forcing_forbidden_move:
            print_winner(game.winner, game.win_by_forcing_forbidden_move)
        print_winner(game.winner)
    else:
        print_board_is_full()


if __name__ == '__main__':
    main()