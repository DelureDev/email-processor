"""
Parser registry — maps format names to parser modules.
To add a new format:
  1. Create parsers/new_format.py with a parse(filepath) function
  2. Add it to PARSERS dict below
"""
from parsers import reso, ingos, luchi, energogarant, energogarant, yugoriya, zetta, alfa, sber, soglasie, vsk, absolut, psb, kaplife, euroins, renins

PARSERS = {
    'reso': reso.parse,
    'yugoriya': yugoriya.parse,
    'zetta': zetta.parse,
    'alfa': alfa.parse,
    'sber': sber.parse,
    'soglasie': soglasie.parse,
    'vsk': vsk.parse,
    'absolut': absolut.parse,
    'psb': psb.parse,
    'kaplife': kaplife.parse,
    'euroins': euroins.parse,
    'renins': renins.parse,
    'ingos': ingos.parse,
    'luchi': luchi.parse,
    'energogarant': energogarant.parse,
    'energogarant': energogarant.parse,
}
