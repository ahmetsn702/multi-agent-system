import asyncio
import sys
sys.path.insert(0, 'multi_agent_system')

from pathlib import Path
from agents.critic_agent import CriticAgent
from core.base_agent import Task

async def test_critic():
    critic = CriticAgent()
    
    screenshot_path = 'multi_agent_system/workspace/projects/browser-tabanl-snake-oyunu-yaz-html-css-/screenshots/page.png'
    project_dir = Path('multi_agent_system/workspace/projects/browser-tabanl-snake-oyunu-yaz-html-css-')
    files = ['index.html', 'script.js', 'static/style.css']
    
    # HTML ve JS dosyalarını oku
    html_content = (project_dir / 'src' / 'index.html').read_text(encoding='utf-8')
    js_content = (project_dir / 'src' / 'script.js').read_text(encoding='utf-8')
    
    task = Task(
        task_id='critic_ui_quality',
        description='Evaluate UI quality from screenshot',
        assigned_to='critic',
        context={
            'screenshot_path': screenshot_path,
            'project_dir': str(project_dir),
            'files': files,
            'content': f'HTML:\n{html_content[:500]}\n\nJavaScript:\n{js_content[:500]}',
            'content_type': 'web_project'
        }
    )
    
    print('[Test] Critic UI quality değerlendirmesi başlatılıyor...')
    thought = await critic.think(task)
    print(f'[Test] Confidence: {thought.confidence}')
    
    result = await critic.act(thought, task)
    print(f'[Test] Success: {result.success}')
    print(f'[Test] Content: {result.content}')
    
    if result.success and isinstance(result.content, dict):
        scores = result.content.get('scores', {})
        print(f'\n[Test] 📊 Scores:')
        for key, value in scores.items():
            print(f'  - {key}: {value}/10')
        print(f'\n[Test] 📈 Average: {result.content.get("average", 0)}/10')
        print(f'[Test] ✅ Approved: {result.content.get("approved", False)}')
        print(f'[Test] 🎯 Routing: {result.content.get("routing", "N/A")}')
        print(f'\n[Test] 📝 Summary: {result.content.get("summary", "")}')
    
    return result

if __name__ == '__main__':
    result = asyncio.run(test_critic())
