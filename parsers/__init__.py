"""
Parser registry — maps format names to parser modules.
To add a new format:
  1. Create parsers/new_format.py with a parse(filepath) function
  2. Add it to PARSERS dict below
"""
from parsers.reso import parse as reso_parse
from parsers.yugoriya import parse as yugoriya_parse
from parsers.zetta import parse as zetta_parse
from parsers.alfa import parse as alfa_parse
from parsers.sber import parse as sber_parse
from parsers.soglasie import parse as soglasie_parse
from parsers.vsk import parse as vsk_parse
from parsers.absolut import parse as absolut_parse
from parsers.psb import parse as psb_parse
from parsers.kaplife import parse as kaplife_parse
from parsers.euroins import parse as euroins_parse
from parsers.renins import parse as renins_parse
from parsers.ingos import parse as ingos_parse
from parsers.luchi import parse as luchi_parse
from parsers.energogarant import parse as energogarant_parse
from parsers.generic_parser import parse as generic_parse

PARSERS = {
    'reso': reso_parse,
    'yugoriya': yugoriya_parse,
    'zetta': zetta_parse,
    'alfa': alfa_parse,
    'sber': sber_parse,
    'soglasie': soglasie_parse,
    'vsk': vsk_parse,
    'absolut': absolut_parse,
    'psb': psb_parse,
    'kaplife': kaplife_parse,
    'euroins': euroins_parse,
    'renins': renins_parse,
    'ingos': ingos_parse,
    'luchi': luchi_parse,
    'energogarant': energogarant_parse,
    'generic_fio': generic_parse,
    'generic_fio_split': generic_parse,
}
