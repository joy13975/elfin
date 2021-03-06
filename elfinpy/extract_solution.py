#!/usr/bin/env python3

# This script takes a solver output JSON and exports a specific solution

import sys
import argparse

try:
    from utilities import *
except ImportError as e:
    from .utilities import *

def parse_args(args):
    desc = 'Exports a specific solution from a solver output JSON.'
    parser = argparse.ArgumentParser(description=desc);
    parser.add_argument('input_path')
    parser.add_argument('output_path')
    return parser.parse_args(args)

def main(test_args=None):
    args = parse_args(sys.argv[1:] if test_args is None else test_args)
    se = SolutionExtractor(args.input_path, args.output_path)
    se.extract()

class SolutionExtractor:
    def __init__(self, input_path, output_path):
        self.input_path = input_path
        self.output_path = output_path

    def extract(self):
        input_json = read_json(self.input_path)
        exporter = input_json['exporter']
        if(exporter != 'elfin-solver'):
            raise ValueError(f'Input file is apparently not generated by elfin-solver. Exporter: \"{exporter}\"');
        self.show_solution_structure(input_json)

        output = self.construct_output(input_json)
        with open(self.output_path, 'w') as output_file:
            json.dump(output,
                output_file,
                separators=(',', ':'),
                ensure_ascii=False,
                indent=4)

    def construct_output(self, input_json):
        print()
        print('***************************************')
        print('**         Specify Extraction        **')
        print('***************************************')

        pg_networks = input_json['pg_networks']
        pg_networks_output = {}
        for pgn_name in pg_networks:
            print(f'Path Guide network \"{pgn_name}\"')
            pgn = pg_networks[pgn_name]
            pgn_output = {}

            for dec_name in pgn:
                print(f'|\n|-- Decimated Area \"{dec_name}\"')
                dec = pgn[dec_name]

                max_sol_idx = len(dec)
                sol_idx = 0
                input_ok = False
                while (not input_ok):
                    sol_idx_input = input(f'Choose between solution indexes #{1} ~ #{max_sol_idx} (default is #1): ') 
                    try:
                        # Default case.
                        if len(sol_idx_input) == 0:
                            sol_idx = 1
                            input_ok = True
                            break

                        sol_idx = int(sol_idx_input)
                        if 1 <= sol_idx <= max_sol_idx:
                            input_ok = True
                        else:
                            raise ValueError('Out of range')
                    except ValueError:
                        print('Invalid input. Try again!')

                sol = dec[sol_idx - 1]
                print(f'Extracting Solution #{sol_idx} {self.rep_solution(sol)}')
                pgn_output[dec_name] = sol

            pg_networks_output[pgn_name] = pgn_output

        output = {'pg_networks': pg_networks_output}
        return output
    
    def show_solution_structure(self, input_json):
        print()
        print('***************************************')
        print('**      Solution file structure      **')
        print('***************************************')

        pg_networks = input_json['pg_networks']
        for pgn_name in pg_networks:
            print(f'Path Guide network \"{pgn_name}\"')
            pgn = pg_networks[pgn_name]
            for dec_name in pgn:
                print(f'|\n|-- Decimated Area \"{dec_name}\"')
                dec = pgn[dec_name]
                sol_idx = 1
                for sol in dec:
                    print(f'|-- -- Solution #{sol_idx} {self.rep_solution(sol)}')
                    sol_idx += 1
            print('')

    def rep_solution(self, sol):
        return f'(checksum {hex(sol["checksum"])[2:].rjust(10)}, score {sol["score"]:.2f})'
    

if __name__ == '__main__':
    main()