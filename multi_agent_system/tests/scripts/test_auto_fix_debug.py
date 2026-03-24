#!/usr/bin/env python3
"""
Test script to debug auto-fix behavior
"""

from agents.coder_agent import CoderAgent

# Create instance
coder = CoderAgent.__new__(CoderAgent)

# Test cases
test_cases = [
    {
        "name": "if b == :",
        "code": "if b == :\n    raise ZeroDivisionError()",
        "expected": "if b == 0:\n    raise ZeroDivisionError()"
    },
    {
        "name": "sys.path.insert(, ...)",
        "code": "sys.path.insert(, os.path.dirname(__file__))",
        "expected": "sys.path.insert(0, os.path.dirname(__file__))"
    },
    {
        "name": "Full main.py example",
        "code": """import sys
from decimal import Decimal

class Divide:
    def compute(self, a, b):
        if b == :
            raise ZeroDivisionError('Sıfıra bölme hatası!')
        return a / b

if __name__ == "__main__":
    sys.path.insert(, os.path.dirname(os.path.abspath(__file__)))
    main()""",
        "expected": """import sys
from decimal import Decimal

class Divide:
    def compute(self, a, b):
        if b == 0:
            raise ZeroDivisionError('Sıfıra bölme hatası!')
        return a / b

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()"""
    }
]

print("=" * 70)
print("AUTO-FIX DEBUG TEST")
print("=" * 70)

for i, test in enumerate(test_cases, 1):
    print(f"\n{'='*70}")
    print(f"TEST {i}: {test['name']}")
    print(f"{'='*70}")
    
    result = coder._auto_fix_common_errors(test['code'])
    
    success = result == test['expected']
    status = "✅ BAŞARILI" if success else "❌ BAŞARISIZ"
    
    print(f"\nDurum: {status}")
    
    if not success:
        print(f"\nBeklenen:\n{test['expected']}")
        print(f"\nAlınan:\n{result}")
        
        # Show diff
        import difflib
        diff = difflib.unified_diff(
            test['expected'].splitlines(keepends=True),
            result.splitlines(keepends=True),
            fromfile='expected',
            tofile='actual',
            lineterm=''
        )
        print("\nFark:")
        print(''.join(diff))

print(f"\n{'='*70}")
print("TEST TAMAMLANDI")
print(f"{'='*70}")
