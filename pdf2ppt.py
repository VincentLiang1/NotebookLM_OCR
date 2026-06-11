"""Entry point: python pdf2ppt.py input.pdf [-o output.pptx] [options]"""
import sys

from pdf2ppt.cli import main

if __name__ == "__main__":
    sys.exit(main())
