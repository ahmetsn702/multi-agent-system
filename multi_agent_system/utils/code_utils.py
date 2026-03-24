import ast
import textwrap

def align_and_validate_chunk(original_code: str, new_chunk: str) -> tuple[bool, str, str]:
    """
    1. Her append chunk geldiğinde önce textwrap.dedent() uygula
    2. Mevcut dosyanın son non-empty satırının indentation seviyesini tespit et
    3. Chunk'ı o seviyeye göre yeniden indent et
    4. Birleşik kodu ast.parse() ile validate et. 
       - Truncation nedeniyle 'unexpected EOF' vb. hatalar normaldir, bunları geçerli say.
       - IndentationError vb. hataları tespit et.
    """
    # 1. new_chunk'ı dedent et
    chunk_dedented = textwrap.dedent(new_chunk)
    # Eğer fazladan bir ilk satır başı varsa kaldır (sadece llm çıktıları için)
    if chunk_dedented.startswith('\n'):
        chunk_dedented = chunk_dedented[1:]
        
    # 2. Son non-empty satırın indentation'ını bul
    lines = original_code.splitlines()
    last_indent = ""
    for line in reversed(lines):
        if line.strip():
            last_indent = line[:len(line) - len(line.lstrip())]
            break
            
    # 3. Yeniden indent et
    indented_chunk = textwrap.indent(chunk_dedented, last_indent)
    
    # 4. Birleşik kodu oluştur ve validate et
    combined = original_code
    if not combined.endswith('\n') and not indented_chunk.startswith('\n'):
        combined += "\n" + indented_chunk
    else:
        # Satır sonu karakterleri çakışmasın diye
        combined = combined.rstrip('\n') + "\n" + indented_chunk
        
    try:
        ast.parse(combined)
        return True, combined, ""
    except SyntaxError as e:
        error_msg = str(e).lower()
        # Truncation devam ettiği için EOF, unterminated string, unclosed vb. syntax hataları geçicidir, geçerli say.
        if any(msg in error_msg for msg in ["unexpected eof", "unterminated string", "unclosed", "incomplete input", "eof while scanning"]):
            return True, combined, ""
            
        return False, combined, f"{type(e).__name__}: {e}"
