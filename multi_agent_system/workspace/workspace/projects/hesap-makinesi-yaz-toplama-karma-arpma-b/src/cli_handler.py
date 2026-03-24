import sys
from typing import List, Optional

def parse_arguments(args: List[str]) -> Optional[str]:
    """
    Komut satiri argumanlarini ayrıştırır.
    
    Args:
        args: sys.argv listesi.
        
    Returns:
        Kullanici komutu veya None.
    """
    try:
        if len(args) > 1:
            return args[1]
        return None
    except Exception as e:
        print(f"Arguman hatasi: {e}")
        return None

def display_help() -> None:
    """
    CLI yardim menüsünü gösterir.
    """
    print("Kullanim: python main.py [komut]")
    print("Komutlar:")
    print("  status - Uygulama durumunu gosterir")
    print("  help   - Bu yardim metnini gosterir")