# SPDX-License-Identifier: AGPL-3.0-only
# Added to this derivative on 2026-10-21.
import unittest
from balance_utils import allowed,format_balance
class Tests(unittest.TestCase):
 def test_permissions(self):
  self.assertTrue(allowed('owner','owner',True))
  self.assertFalse(allowed('other','owner',True))
  self.assertFalse(allowed('owner','owner',False))
 def test_amounts(self):
  s=format_balance({'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':'12.34','granted_balance':'2.00','topped_up_balance':'10.34'}]})
  self.assertIn('12.34',s)
  self.assertIn('CNY',s)
if __name__=='__main__': unittest.main()
