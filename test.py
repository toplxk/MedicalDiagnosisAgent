# -*- coding: utf-8 -*-
# @author: lixiaokai1
# @description:
# @date: 2026/8/25 21:03
# @file: test.py

import textwrap

def wrap ( string, max_width ) :
    # chunk = ''
    # for i in range(0, len(string), max_width):
    #     chunk += string[i:i + max_width] + '\n'
    # return chunk;
    return textwrap.fill(string, max_width)
if __name__ == '__main__' :
    string, max_width = input (), int ( input())
    result = wrap ( string, max_width )
    print(result)