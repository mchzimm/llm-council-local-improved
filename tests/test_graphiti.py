#!/usr/bin/env python3
"""
Graphiti MCP Server Integration Tests

Tests the knowledge graph memory capabilities:
1. Adding memories (episodes)
2. Searching/retrieving memories
3. Inference from related facts

NOTE: Graphiti requires:
- FalkorDB/Neo4j database running
- LLM API key (OpenAI, etc.) for entity extraction
- Episode processor must be running to process queued episodes
"""

import asyncio
import json
import sys
from typing import Dict, Any, List


def _print_raw_json(label: str, result: Dict[str, Any]):
    """Print raw JSON response for debugging."""
    print(f"\n   📋 RAW JSON ({label}):")
    print("-" * 50)
    try:
        print(json.dumps(result, indent=2, default=str))
    except:
        print(str(result))
    print("-" * 50)


async def run_graphiti_test():
    """Run the Graphiti memory test sequence."""
    from backend.mcp.registry import get_mcp_registry
    
    print("=" * 60)
    print("GRAPHITI KNOWLEDGE GRAPH TEST")
    print("=" * 60)
    
    # Initialize MCP registry
    print("\n[1/7] Initializing MCP servers...")
    registry = get_mcp_registry()
    status = await registry.initialize()
    
    if 'graphiti' not in status.get('servers', []):
        print("❌ FAILED: Graphiti server not available")
        print("   Make sure Graphiti is running at http://localhost:8000")
        await registry.shutdown()
        return False
    
    print("✅ Graphiti server connected")
    print(f"   Tools: {[t.split('.')[-1] for t in status.get('tools', []) if 'graphiti' in t]}")
    
    # Check server status
    print("\n[2/7] Checking Graphiti server status...")
    try:
        status_result = await registry.call_tool('graphiti.get_status', {})
        _print_raw_json("get_status", status_result)
        if not status_result.get('success'):
            print(f"   ❌ Status check failed")
            await registry.shutdown()
            return False
        print(f"   ✅ Status: {_extract_message(status_result)}")
    except Exception as e:
        print(f"   ❌ Status check failed: {e}")
        await registry.shutdown()
        return False
    
    # Test group ID - separate from production to avoid data conflicts
    test_group = "test_graphiti"
    
    # Clear existing data first
    print(f"\n[3/7] Clearing existing graph data...")
    try:
        clear_result = await registry.call_tool('graphiti.clear_graph', {
            'group_id': test_group
        })
        _print_raw_json("clear_graph", clear_result)
        if clear_result.get('success'):
            print("   ✅ Graph cleared successfully")
        else:
            print(f"   ⚠️ Clear failed (may be empty): {clear_result.get('error')}")
    except Exception as e:
        print(f"   ⚠️ Clear failed (may be empty): {e}")
    
    # Wait a moment for clear to complete
    await asyncio.sleep(2)
    
    # Define test memories
    memories = [
        ("jane_preference_1", "Jane likes her New Balance shoes"),
        ("jane_preference_2", "Jane likes her Nike shoes"),
        ("jane_preference_3", "Jane has Nike clothes"),
        ("jane_preference_4", "Jane likes Adidas shoes"),
        ("jane_preference_5", "Jane thinks Adidas shoes are ok but she likes the brand of shoes better that she has clothes from")
    ]
    
    # Add all memories
    print("\n[4/7] Adding memories...")
    for i, (name, memory) in enumerate(memories, 1):
        try:
            result = await registry.call_tool('graphiti.add_memory', {
                'name': name,
                'episode_body': memory,
                'group_id': test_group,
                'source': 'text',
                'source_description': 'User preference observation'
            })
            _print_raw_json(f"add_memory [{i}/5]", result)
            
            if not result.get('success'):
                print(f"   ❌ [{i}/5] Failed: {result.get('error')}")
                await registry.shutdown()
                return False
                
            msg = _extract_message(result)
            status_icon = "⏳" if "queued" in msg.lower() else "✅"
            print(f"   {status_icon} [{i}/5] \"{memory[:45]}...\"")
        except Exception as e:
            print(f"   ❌ [{i}/5] Exception: {e}")
            await registry.shutdown()
            return False
    
    # Wait for processing - each episode takes ~25s with local LLM
    print("\n   Waiting for graph processing...")
    print("   (Each episode takes ~25s to process with local LLM)")
    total_wait = 150  # 5 episodes * 25s + buffer
    for i in range(0, total_wait, 15):
        await asyncio.sleep(15)
        print(f"      ... {i+15}s / {total_wait}s")
    
    # Validate memories were created
    print("\n[5/7] Validating knowledge graph data...")
    
    validation_passed = False
    
    # Check episodes
    print("\n   a) Checking episodes...")
    try:
        episodes_result = await registry.call_tool('graphiti.get_episodes', {
            'group_ids': [test_group],
            'max_episodes': 20
        })
        _print_raw_json("get_episodes", episodes_result)
        
        if not episodes_result.get('success'):
            print(f"   ❌ Get episodes failed: {episodes_result.get('error')}")
            await registry.shutdown()
            return False
            
        episodes = _extract_episodes(episodes_result)
        if episodes:
            print(f"   ✅ Found {len(episodes)} episodes")
            for ep in episodes[:5]:
                print(f"      - {ep}")
        else:
            print("   ⚠️  No episodes found")
    except Exception as e:
        print(f"   ❌ Get episodes exception: {e}")
        await registry.shutdown()
        return False
    
    # Check nodes
    print("\n   b) Checking nodes...")
    try:
        nodes_result = await registry.call_tool('graphiti.search_nodes', {
            'query': 'Jane shoes Nike Adidas preferences brands',
            'group_ids': [test_group],
            'max_nodes': 20
        })
        _print_raw_json("search_nodes (validation)", nodes_result)
        
        if not nodes_result.get('success'):
            print(f"   ❌ Node search failed: {nodes_result.get('error')}")
            await registry.shutdown()
            return False
            
        nodes = _extract_nodes(nodes_result)
        if nodes:
            print(f"   ✅ Found {len(nodes)} nodes:")
            for node in nodes[:5]:
                print(f"      - {node.get('name', 'unknown')}: {node.get('summary', '')[:50]}...")
            validation_passed = True
        else:
            print("   ❌ No nodes found - graph not populated")
    except Exception as e:
        print(f"   ❌ Node search exception: {e}")
        await registry.shutdown()
        return False
    
    # Check facts
    print("\n   c) Checking facts...")
    try:
        facts_result = await registry.call_tool('graphiti.search_memory_facts', {
            'query': 'Jane likes shoes brands preferences',
            'group_ids': [test_group],
            'max_facts': 20
        })
        _print_raw_json("search_memory_facts (validation)", facts_result)
        
        if not facts_result.get('success'):
            print(f"   ❌ Fact search failed: {facts_result.get('error')}")
            await registry.shutdown()
            return False
            
        facts = _extract_facts(facts_result)
        if facts:
            print(f"   ✅ Found {len(facts)} facts:")
            for fact in facts[:5]:
                print(f"      - {fact}")
            validation_passed = True
        else:
            print("   ⚠️  No facts found")
    except Exception as e:
        print(f"   ❌ Fact search exception: {e}")
        await registry.shutdown()
        return False
    
    # Run final query only if validation passed
    if not validation_passed:
        print("\n" + "=" * 60)
        print("❌ VALIDATION FAILED")
        print("=" * 60)
        print("Cannot run final query - no nodes or facts in knowledge graph.")
        print("Check that Graphiti is properly configured with:")
        print("  - LLM API key (OpenAI, etc.)")
        print("  - Episode processor running")
        print("  - Database connection working")
        await registry.shutdown()
        return False
    
    # Final query
    print("\n" + "=" * 60)
    print("[6/7] FINAL QUERY: Which shoe brand does Jane like best?")
    print("=" * 60)
    
    print("\n   Searching facts for answer...")
    try:
        facts_result = await registry.call_tool('graphiti.search_memory_facts', {
            'query': 'Which shoe brand does Jane like the best?',
            'group_ids': [test_group],
            'max_facts': 10
        })
        _print_raw_json("search_memory_facts (final query)", facts_result)
        facts = _extract_facts(facts_result)
        
        print("\n   📊 RELEVANT FACTS:")
        if facts:
            for fact in facts:
                print(f"      • {fact}")
        else:
            print("      (no facts returned)")
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
    
    print("\n   Searching nodes for answer...")
    try:
        nodes_result = await registry.call_tool('graphiti.search_nodes', {
            'query': 'Jane favorite best preferred shoe brand',
            'group_ids': [test_group],
            'max_nodes': 10
        })
        _print_raw_json("search_nodes (final query)", nodes_result)
        nodes = _extract_nodes(nodes_result)
        
        print("\n   📊 RELEVANT NODES:")
        if nodes:
            for node in nodes:
                print(f"      • {node.get('name', 'unknown')}: {node.get('summary', '')[:60]}...")
        else:
            print("      (no nodes returned)")
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
    
    # Expected answer analysis
    print("\n" + "-" * 60)
    print("[7/7] EXPECTED ANSWER: Nike")
    print("   REASONING:")
    print("      - Jane has Nike clothes")
    print("      - Jane prefers shoes from the brand she has clothes from")
    print("      - Therefore: Jane likes Nike shoes best")
    print("-" * 60)
    
    await registry.shutdown()
    print("\n✅ Test complete")
    return True


def _extract_message(result: Dict[str, Any]) -> str:
    """Extract message from tool result."""
    if not result.get('success'):
        return f"Error: {result.get('error', 'unknown')}"
    
    output = result.get('output', {})
    content = output.get('content', [])
    
    if content and isinstance(content, list):
        for item in content:
            if item.get('type') == 'text':
                try:
                    data = json.loads(item.get('text', '{}'))
                    if 'message' in data:
                        return data['message']
                    if 'result' in data and isinstance(data['result'], dict):
                        return data['result'].get('message', str(data['result']))
                    if 'status' in data:
                        return f"{data.get('status')}: {data.get('message', '')}"
                    return str(data)[:100]
                except:
                    return item.get('text', '')[:100]
    
    return str(output)[:100]


def _extract_episodes(result: Dict[str, Any]) -> List[str]:
    """Extract episodes from result."""
    if not result.get('success'):
        return []
    
    output = result.get('output', {})
    content = output.get('content', [])
    
    if content and isinstance(content, list):
        for item in content:
            if item.get('type') == 'text':
                try:
                    data = json.loads(item.get('text', '{}'))
                    episodes = data.get('result', data).get('episodes', [])
                    return [f"{e.get('name', 'unknown')}: {e.get('content', '')[:50]}..." for e in episodes]
                except:
                    pass
    return []


def _extract_nodes(result: Dict[str, Any]) -> List[Dict]:
    """Extract nodes from search result."""
    if not result.get('success'):
        return []
    
    output = result.get('output', {})
    content = output.get('content', [])
    
    if content and isinstance(content, list):
        for item in content:
            if item.get('type') == 'text':
                try:
                    data = json.loads(item.get('text', '{}'))
                    if 'result' in data:
                        return data['result'].get('nodes', [])
                    return data.get('nodes', [])
                except:
                    pass
    return []


def _extract_facts(result: Dict[str, Any]) -> List[str]:
    """Extract facts from search result."""
    if not result.get('success'):
        return []
    
    output = result.get('output', {})
    content = output.get('content', [])
    
    if content and isinstance(content, list):
        for item in content:
            if item.get('type') == 'text':
                try:
                    data = json.loads(item.get('text', '{}'))
                    facts_data = data.get('result', data).get('facts', [])
                    formatted = []
                    for f in facts_data:
                        if isinstance(f, dict):
                            fact_str = f.get('fact', f.get('name', str(f)))
                            formatted.append(fact_str[:100])
                        else:
                            formatted.append(str(f)[:100])
                    return formatted
                except:
                    pass
    return []


if __name__ == "__main__":
    success = asyncio.run(run_graphiti_test())
    sys.exit(0 if success else 1)
