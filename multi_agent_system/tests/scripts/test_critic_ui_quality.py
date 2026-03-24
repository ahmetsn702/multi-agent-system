"""
Manual test for Critic UI Quality evaluation
"""
import asyncio
import pytest
from pathlib import Path
from agents.critic_agent import CriticAgent
from core.base_agent import Task

@pytest.mark.asyncio
async def test_critic_ui_quality():
    """Test Critic with screenshot"""
    
    # Initialize Critic
    critic = CriticAgent()
    
    # Screenshot path from previous successful test
    screenshot_path = "workspace/projects/html-ile-mavi-renkli-basit-sayfa-yaz/screenshots/page.png"
    project_dir = "workspace/projects/html-ile-mavi-renkli-basit-sayfa-yaz"
    files = ["web_generator.py", "index.html"]
    
    # Create task
    task = Task(
        task_id="test_critic_ui",
        description="Evaluate UI quality from screenshot",
        assigned_to="critic",
        context={
            "screenshot_path": screenshot_path,
            "project_dir": project_dir,
            "files": files,
        }
    )
    
    print("=" * 80)
    print("Testing CriticAgent with UI Screenshot")
    print("=" * 80)
    
    # Check if screenshot exists
    if Path(screenshot_path).exists():
        print(f"\n✅ Screenshot exists: {screenshot_path}")
        print(f"   Size: {Path(screenshot_path).stat().st_size} bytes")
    else:
        print(f"\n❌ Screenshot NOT found: {screenshot_path}")
        return
    
    # Think
    print("\n1. THINK phase:")
    thought = await critic.think(task)
    print(f"   Reasoning: {thought.reasoning[:200]}...")
    print(f"   Confidence: {thought.confidence}")
    
    # Act
    print("\n2. ACT phase:")
    result = await critic.act(thought, task)
    print(f"   Success: {result.success}")
    print(f"   Content type: {type(result.content)}")
    if isinstance(result.content, dict):
        print(f"   Content keys: {result.content.keys()}")
    else:
        print(f"   Content: {str(result.content)[:200]}...")
    
    # Check scores
    scores = None
    if isinstance(result.content, dict) and "scores" in result.content:
        scores = result.content["scores"]
    elif result.metadata.get("scores"):
        scores = result.metadata["scores"]
    
    if scores:
        print(f"\n📊 SCORES:")
        for key, value in scores.items():
            print(f"   {key}: {value}/10")
        
        if "ui_quality" in scores:
            print(f"\n✅ UI Quality score found: {scores['ui_quality']}/10")
        else:
            print(f"\n⚠️  UI Quality score NOT found")
    else:
        print("\n⚠️  No scores found")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(test_critic_ui_quality())
