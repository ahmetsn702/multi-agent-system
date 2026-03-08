import asyncio
import sys
sys.path.insert(0, 'multi_agent_system')

from pathlib import Path
from agents.ui_tester_agent import UITesterAgent
from core.base_agent import Task

async def test_ui():
    ui_tester = UITesterAgent()
    
    project_dir = Path('multi_agent_system/workspace/projects/browser-tabanl-snake-oyunu-yaz-html-css-')
    files = ['index.html', 'script.js', 'static/style.css']
    
    task = Task(
        task_id='ui_test_snake',
        description='Test Snake game UI',
        assigned_to='ui_tester',
        context={
            'project_dir': str(project_dir),
            'files': files,
            'project_slug': 'browser-tabanl-snake-oyunu-yaz-html-css-'
        }
    )
    
    print('[Test] UI Tester başlatılıyor...')
    thought = await ui_tester.think(task)
    print(f'[Test] Confidence: {thought.confidence}')
    print(f'[Test] Plan: {thought.plan}')
    
    result = await ui_tester.act(thought, task)
    print(f'[Test] Success: {result.success}')
    print(f'[Test] Content: {result.content}')
    print(f'[Test] Screenshot: {result.metadata.get("screenshot_path")}')
    
    return result

if __name__ == '__main__':
    result = asyncio.run(test_ui())
