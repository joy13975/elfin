#!/usr/bin/env python3

#
# A PyMol extension script template
#

def main():
    """main"""
    raise RuntimeError('This module should not be executed as a script')

if __name__ =='__main__': 
    main()

in_pymol = False
try:
    import pymol
    in_pymol = True
except ImportError as ie:
    main()

if in_pymol:
    from pymol import cmd

    print('Template Extension Loaded')