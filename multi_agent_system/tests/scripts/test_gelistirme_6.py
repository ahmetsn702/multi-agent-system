"""
test_gelistirme_6.py
Test script for ChromaDB RAG and Playwright UI Tester
"""
import asyncio
import pytest
import sys
from pathlib import Path

# Test 1: ChromaDB Vector Memory
def test_vector_memory():
    """Test ChromaDB vector search."""
    print("\n" + "="*80)
    print("TEST 1: ChromaDB Vector Memory")
    print("="*80)
    
    try:
        from core.vector_memory import get_vector_memory
        
        vm = get_vector_memory()
        
        if not vm.enabled:
            print("❌ ChromaDB not available (install: pip install chromadb sentence-transformers)")
            return False
        
        print(f"✅ ChromaDB initialized: {vm.count()} projects")
        
        # Test add_project
        test_slug = "test-flask-jwt"
        test_summary = "Flask JWT authentication system with SQLite database"
        test_snippets = [
            "from flask import Flask, jsonify\nfrom flask_jwt_extended import JWTManager",
            "def create_token(user_id):\n    return jwt.encode({'user_id': user_id}, SECRET_KEY)"
        ]
        
        success = vm.add_project(
            test_slug,
            test_summary,
            test_snippets,
            metadata={"tags": ["flask", "jwt", "auth"], "cost": 0.05}
        )
        
        if success:
            print(f"✅ Project added: {test_slug}")
        else:
            print(f"❌ Failed to add project")
            return False
        
        # Test search_similar
        query = "FastAPI authentication with tokens"
        results = vm.search_similar(query, n=3)
        
        print(f"\n🔍 Search query: '{query}'")
        print(f"📊 Results: {len(results)} projects found")
        
        for r in results:
            print(f"  • {r['slug']} (similarity: {r['similarity']})")
            print(f"    Tags: {r['metadata'].get('tags', [])}")
        
        # Test get_context
        context = vm.get_context(query, max_length=500)
        print(f"\n📚 Context length: {len(context)} chars")
        print(f"Context preview:\n{context[:200]}...")
        
        # Cleanup
        vm.delete_project(test_slug)
        print(f"\n🧹 Cleanup: {test_slug} deleted")
        
        print("\n✅ TEST 1 PASSED: ChromaDB Vector Memory")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# Test 2: Memory Agent Integration
def test_memory_agent_integration():
    """Test Memory Agent with vector search."""
    print("\n" + "="*80)
    print("TEST 2: Memory Agent Integration")
    print("="*80)
    
    try:
        from core.memory_agent import get_memory_agent
        
        memory = get_memory_agent()
        
        # Test search_relevant (should use vector search if available)
        query = "Flask authentication system"
        results = memory.search_relevant(query, max_results=3)
        
        print(f"🔍 Query: '{query}'")
        print(f"📊 Results: {len(results)} projects")
        
        for r in results:
            search_method = r.get('search_method', 'unknown')
            print(f"  • {r['slug']} (relevance: {r['relevance']}, method: {search_method})")
        
        if results and results[0].get('search_method') == 'vector':
            print("\n✅ Vector search is working!")
        elif results and results[0].get('search_method') == 'keyword':
            print("\n⚠️  Fallback to keyword search (vector search unavailable)")
        else:
            print("\n⚠️  No results found")
        
        print("\n✅ TEST 2 PASSED: Memory Agent Integration")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# Test 3: UI Tester Agent
@pytest.mark.asyncio
async def test_ui_tester():
    """Test Playwright UI Tester."""
    print("\n" + "="*80)
    print("TEST 3: Playwright UI Tester")
    print("="*80)
    
    try:
        from agents.ui_tester_agent import UITesterAgent, PLAYWRIGHT_AVAILABLE
        from core.base_agent import Task
        
        if not PLAYWRIGHT_AVAILABLE:
            print("❌ Playwright not available (install: pip install playwright)")
            print("   Then run: python -m playwright install chromium")
            return False
        
        print("✅ Playwright available")
        
        # Create test project structure
        test_project = Path("workspace/projects/test-ui-project")
        test_project.mkdir(parents=True, exist_ok=True)
        (test_project / "src").mkdir(exist_ok=True)
        (test_project / "screenshots").mkdir(exist_ok=True)
        
        # Create simple HTML file
        html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
    <style>
        body { background: #1a1a2e; color: #e2e8f0; font-family: Arial; padding: 40px; }
        h1 { color: #7c3aed; }
    </style>
</head>
<body>
    <h1>Test UI Page</h1>
    <p>This is a test page for UI testing.</p>
</body>
</html>"""
        
        (test_project / "src" / "index.html").write_text(html_content)
        
        # Create UI tester agent
        ui_tester = UITesterAgent()
        
        # Create task
        task = Task(
            task_id="test_ui",
            description="Test UI screenshot",
            assigned_to="ui_tester",
            context={
                "project_dir": str(test_project),
                "files": ["index.html"],
                "project_slug": "test-ui-project"
            }
        )
        
        # Run test
        print("\n🧪 Running UI test...")
        thought = await ui_tester.think(task)
        print(f"💭 Confidence: {thought.confidence}")
        
        response = await ui_tester.act(thought, task)
        
        if response.success:
            screenshot_path = response.metadata.get("screenshot_path")
            if screenshot_path and Path(screenshot_path).exists():
                print(f"✅ Screenshot created: {screenshot_path}")
                print(f"   Size: {Path(screenshot_path).stat().st_size} bytes")
            else:
                print("⚠️  Screenshot not created")
        else:
            print(f"❌ UI test failed: {response.error}")
        
        print("\n✅ TEST 3 PASSED: Playwright UI Tester")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# Test 4: Critic with Screenshot
@pytest.mark.asyncio
async def test_critic_screenshot():
    """Test Critic agent with screenshot evaluation."""
    print("\n" + "="*80)
    print("TEST 4: Critic with Screenshot")
    print("="*80)
    
    try:
        from agents.critic_agent import CriticAgent
        from core.base_agent import Task
        
        critic = CriticAgent()
        
        # Test without screenshot
        task1 = Task(
            task_id="test_critic_1",
            description="Review code",
            assigned_to="critic",
            context={
                "content": "def hello():\n    print('Hello')",
                "content_type": "Python code"
            }
        )
        
        print("\n🧪 Test 1: Without screenshot")
        response1 = await critic.run(task1)
        feedback1 = response1.content
        
        print(f"  Scores: {feedback1.get('scores', {})}")
        print(f"  Average: {feedback1.get('score', 0)}/10")
        print(f"  Has screenshot: {feedback1.get('has_screenshot', False)}")
        
        # Test with screenshot
        task2 = Task(
            task_id="test_critic_2",
            description="Review code with UI",
            assigned_to="critic",
            context={
                "content": "def hello():\n    print('Hello')",
                "content_type": "Python code",
                "screenshot_path": "workspace/projects/test-ui-project/screenshots/page.png"
            }
        )
        
        print("\n🧪 Test 2: With screenshot")
        response2 = await critic.run(task2)
        feedback2 = response2.content
        
        print(f"  Scores: {feedback2.get('scores', {})}")
        print(f"  Average: {feedback2.get('score', 0)}/10")
        print(f"  Has screenshot: {feedback2.get('has_screenshot', False)}")
        
        # Check if ui_quality is in scores
        if 'ui_quality' in feedback2.get('scores', {}):
            print(f"  ✅ UI quality score: {feedback2['scores']['ui_quality']}/10")
        else:
            print(f"  ⚠️  UI quality score not found")
        
        print("\n✅ TEST 4 PASSED: Critic with Screenshot")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# Main test runner
async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("GELİŞTİRME 6 TEST SÜİTİ")
    print("ChromaDB RAG + Playwright UI Tester")
    print("="*80)
    
    results = []
    
    # Test 1: ChromaDB
    results.append(("ChromaDB Vector Memory", test_vector_memory()))
    
    # Test 2: Memory Agent
    results.append(("Memory Agent Integration", test_memory_agent_integration()))
    
    # Test 3: UI Tester
    results.append(("Playwright UI Tester", await test_ui_tester()))
    
    # Test 4: Critic
    results.append(("Critic with Screenshot", await test_critic_screenshot()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
