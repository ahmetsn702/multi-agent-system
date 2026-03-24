"""
Manual test for UITesterAgent
"""
import asyncio
import pytest
from pathlib import Path
from agents.ui_tester_agent import UITesterAgent
from core.base_agent import Task

@pytest.mark.asyncio
async def test_ui_tester():
    """Test UI Tester with green HTML project"""
    
    # Initialize UI Tester
    ui_tester = UITesterAgent()
    
    # Project info
    project_dir = Path("workspace/projects/html-ile-ye-il-renkli-basit-sayfa-yaz")
    files = ["generator.py", "index.html"]
    
    # Create task
    task = Task(
        task_id="test_ui",
        description="Test UI for green HTML project",
        assigned_to="ui_tester",
        context={
            "project_dir": str(project_dir),
            "files": files,
            "project_slug": "html-ile-ye-il-renkli-basit-sayfa-yaz"
        }
    )
    
    print("=" * 80)
    print("Testing UITesterAgent")
    print("=" * 80)
    
    # Think
    print("\n1. THINK phase:")
    thought = await ui_tester.think(task)
    print(f"   Reasoning: {thought.reasoning[:200]}...")
    print(f"   Confidence: {thought.confidence}")
    print(f"   Plan: {thought.plan}")
    
    # Act
    print("\n2. ACT phase:")
    result = await ui_tester.act(thought, task)
    print(f"   Success: {result.success}")
    print(f"   Content: {result.content}")
    print(f"   Metadata: {result.metadata}")
    
    # Check screenshot
    if result.metadata.get("screenshot_path"):
        screenshot_path = Path(result.metadata["screenshot_path"])
        if screenshot_path.exists():
            print(f"\n✅ Screenshot exists: {screenshot_path}")
            print(f"   Size: {screenshot_path.stat().st_size} bytes")
        else:
            print(f"\n❌ Screenshot NOT found: {screenshot_path}")
    else:
        print("\n⚠️  No screenshot path in metadata")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(test_ui_tester())
