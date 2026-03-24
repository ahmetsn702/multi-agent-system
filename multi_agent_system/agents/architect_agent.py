"""
agents/architect_agent.py
Architect Agent generates project contracts that define data models, APIs,
file structure, and shared constants for consistent code generation.
"""
import json
import re
from pathlib import Path
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus


SYSTEM_PROMPT = """You are the Architect Agent in MAOS — Multi-Agent Orchestration System.

Your role is to analyze a user goal and task plan, then generate a comprehensive project contract that defines the architecture for all code generation. This contract is the single source of truth that ensures consistency across multiple coder agents.

## Core Responsibility

Generate a JSON contract that specifies:
1. Data models with EXACT field names and types
2. API endpoints with precise input/output schemas
3. File structure with clear responsibilities
4. Shared constants and type definitions

## Critical Requirements

**Consistency is paramount.** Every field name, type, and interface you define will be used by multiple agents. Inconsistencies will cause integration failures.

**Be specific, not vague.** Do not write "user data" — write exact field names like "user_id", "username", "email". Do not write "string" — write "str" or "Optional[str]".

**Think about interfaces.** If one file exports a class, and another file imports it, the class name must match exactly. If an API endpoint returns data, the output schema must match the data model fields.

**Use standard types.** Prefer Python built-in types: str, int, float, bool, list, dict, Optional, Union. For custom types, define them in shared_constants.

## Output Format

Return ONLY valid JSON. No markdown, no explanations, no prose. Just the JSON contract.

```json
{
  "data_models": [
    {
      "name": "User",
      "description": "Represents a system user",
      "fields": [
        {"name": "user_id", "type": "int", "required": true, "description": "Unique identifier"},
        {"name": "username", "type": "str", "required": true, "description": "Login name"},
        {"name": "email", "type": "Optional[str]", "required": false, "description": "Contact email"}
      ]
    }
  ],
  "api_endpoints": [
    {
      "path": "/api/users",
      "method": "GET",
      "description": "List all users",
      "input_schema": {
        "limit": "int",
        "offset": "int"
      },
      "output_schema": {
        "users": "list[User]",
        "total": "int"
      }
    }
  ],
  "file_structure": [
    {
      "path": "src/models.py",
      "responsibility": "Define all data models (User, Post, Comment)",
      "exports": ["User", "Post", "Comment"]
    },
    {
      "path": "src/api.py",
      "responsibility": "Implement all API endpoints",
      "exports": ["app", "get_users", "create_user"]
    }
  ],
  "shared_constants": {
    "MAX_USERNAME_LENGTH": 50,
    "DEFAULT_PAGE_SIZE": 20,
    "UserRole": "Literal['admin', 'user', 'guest']"
  }
}
```

## Behavior Guidelines

1. **Analyze the goal**: Identify what data the system manages, what operations it performs, what interfaces it exposes
2. **Identify entities**: Extract nouns from the goal (User, Post, Order, Product) — these become data models
3. **Identify operations**: Extract verbs from the goal (create, list, update, delete) — these become API endpoints or functions
4. **Plan file structure**: Group related functionality (models in one file, API in another, utilities in a third)
5. **Define constants**: Extract magic numbers, enums, and type aliases that will be reused

## Common Patterns

**CRUD API**: For each entity, define GET (list/detail), POST (create), PUT (update), DELETE endpoints
**Data validation**: Use type hints like Optional, Union, Literal to express constraints
**File organization**: Separate concerns (models, business logic, API, utilities, tests)
**Naming conventions**: snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants

## Quality Checklist

Before returning your contract, verify:
- [ ] All field names are specific and descriptive
- [ ] All types are concrete (no "string", use "str")
- [ ] API input/output schemas reference defined data models
- [ ] File exports match what other files will import
- [ ] Shared constants are actually shared (used in multiple places)
- [ ] The JSON is valid and parseable

Remember: This contract will be read by multiple coder agents. Clarity and consistency prevent integration bugs.
"""


class ArchitectAgent(BaseAgent):
    """
    Generates project contracts that define data models, APIs, file structure,
    and shared constants for consistent code generation across multiple agents.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="architect",
            name="Mimar Ajan",
            role="Mimari Tasarım ve Sözleşme Üretimi",
            description="Proje mimarisini analiz eder ve tüm kod üretimi için tutarlı bir sözleşme oluşturur.",
            capabilities=["architecture_design", "contract_generation", "interface_design"],
            bus=bus,
        )

    def _serialize_plan(self, plan) -> str:
        """
        Safely serialize plan to JSON string, handling Task objects.
        
        Args:
            plan: Plan object (dict, list, or other)
            
        Returns:
            JSON string representation of the plan
        """
        def task_to_dict(obj):
            """Convert Task objects to dictionaries for JSON serialization."""
            if hasattr(obj, '__dict__'):
                # Check if it's a Task object
                if hasattr(obj, 'task_id') and hasattr(obj, 'description'):
                    return {
                        "task_id": getattr(obj, 'task_id', ''),
                        "description": getattr(obj, 'description', ''),
                        "assigned_to": getattr(obj, 'assigned_to', ''),
                        "dependencies": getattr(obj, 'dependencies', []),
                    }
                # For other objects with __dict__, return the dict
                return obj.__dict__
            return obj
        
        try:
            # Try to serialize with custom handler for Task objects
            if isinstance(plan, dict):
                # Handle dict with potential Task objects in values
                serializable_plan = {}
                for key, value in plan.items():
                    if isinstance(value, list):
                        serializable_plan[key] = [task_to_dict(item) for item in value]
                    else:
                        serializable_plan[key] = task_to_dict(value)
                return json.dumps(serializable_plan, indent=2, default=task_to_dict)
            elif isinstance(plan, list):
                # Handle list of Task objects
                return json.dumps([task_to_dict(item) for item in plan], indent=2, default=task_to_dict)
            else:
                # Try direct serialization with fallback
                return json.dumps(plan, indent=2, default=task_to_dict)
        except (TypeError, ValueError):
            # Fallback to string representation
            return str(plan)

    async def think(self, task: Task) -> ThoughtProcess:
        """
        Analyze the user goal and plan to determine what needs to be in the contract.

        Args:
            task: Task containing user_goal and plan in context

        Returns:
            ThoughtProcess with reasoning about contract structure
        """
        user_goal = task.context.get("user_goal", "")
        plan = task.context.get("plan", {})

        # Safely serialize plan (handle Task objects)
        plan_summary = self._serialize_plan(plan)

        # Build analysis prompt
        analysis_prompt = f"""Analyze this project goal and plan to identify:
1. What data models are needed (entities, their fields and types)
2. What API endpoints or functions are needed (operations)
3. How files should be organized (responsibilities)
4. What constants or types should be shared

User Goal: {user_goal}

Plan: {plan_summary}

Provide a brief analysis of the architecture."""

        reasoning = await self._call_llm(
            messages=[{"role": "user", "content": analysis_prompt}],
            system_prompt="You are analyzing a project to plan its architecture. Be concise.",
            temperature=0.3,
            max_tokens=500,
        )

        return ThoughtProcess(
            reasoning=reasoning,
            plan=["Generate contract JSON", "Validate schema", "Save to file"],
            tool_calls=[],
            confidence=0.9,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """
        Generate the project contract JSON and save it to the project directory.

        Args:
            thought: The analysis from think()
            task: Task containing user_goal, plan, and project_slug

        Returns:
            AgentResponse with contract content and file path
        """
        user_goal = task.context.get("user_goal", "")
        plan = task.context.get("plan", {})
        project_slug = task.context.get("project_slug", "")

        if not project_slug:
            return AgentResponse(
                content=None,
                success=False,
                error="Missing project_slug in task context",
            )

        # Generate contract with retry logic
        contract = await self._generate_contract_with_retry(user_goal, plan)

        if not contract:
            return AgentResponse(
                content=None,
                success=False,
                error="Failed to generate valid contract after 3 retries",
            )

        # Validate contract schema
        validation_errors = self._validate_contract(contract)
        if validation_errors:
            return AgentResponse(
                content=None,
                success=False,
                error=f"Contract validation failed: {', '.join(validation_errors)}",
            )

        # DEBUG: Print contract before saving
        print(f"[Architect DEBUG] Final contract before saving:")
        print(f"[Architect DEBUG] data_models: {len(contract.get('data_models', []))} items")
        print(f"[Architect DEBUG] api_endpoints: {len(contract.get('api_endpoints', []))} items")
        print(f"[Architect DEBUG] file_structure: {len(contract.get('file_structure', []))} items")
        print(f"[Architect DEBUG] shared_constants: {len(contract.get('shared_constants', {}))} items")
        print(f"[Architect DEBUG] Full contract: {json.dumps(contract, indent=2)}")

        # Save contract to file
        contract_path = Path("workspace/projects") / project_slug / "contract.json"
        try:
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            contract_path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
        except Exception as e:
            return AgentResponse(
                content=None,
                success=False,
                error=f"Failed to write contract file: {e}",
            )

        return AgentResponse(
            content=contract,
            success=True,
            metadata={"contract_path": str(contract_path)},
        )

    async def _generate_contract_with_retry(
        self, user_goal: str, plan: dict, max_retries: int = 3
    ) -> Optional[dict]:
        """
        Generate contract with retry logic for invalid responses.

        Args:
            user_goal: User's project goal
            plan: Task plan from planner
            max_retries: Maximum number of retry attempts

        Returns:
            Contract dict or None if all retries fail
        """
        # Build contract generation prompt
        plan_summary = self._serialize_plan(plan)
        
        # Create a more detailed prompt with explicit instructions
        base_prompt = f"""You are designing the architecture for a software project.

USER GOAL:
{user_goal}

TASK PLAN:
{plan_summary}

YOUR TASK:
Analyze the goal and plan above, then generate a comprehensive project contract in JSON format.

The contract MUST include:

1. DATA MODELS: Identify all entities/objects the system will manage
   - For each entity, define exact field names and Python types
   - Example: User, Post, Order, Product, etc.

2. API ENDPOINTS (if applicable): Define all API routes or main functions
   - Specify HTTP method, path, input parameters, and output format
   - Example: GET /api/users, POST /api/orders, etc.

3. FILE STRUCTURE: Plan which Python files to create
   - Specify the file path (e.g., src/models.py, src/api.py)
   - Describe each file's responsibility
   - List what classes/functions each file exports

4. SHARED CONSTANTS: Define any constants, enums, or type aliases
   - Example: MAX_RETRIES = 3, Status = Literal['active', 'inactive']

IMPORTANT:
- Return ONLY the JSON contract, no markdown code blocks
- Do NOT return empty arrays - analyze the goal and fill in actual data
- Be specific with field names and types
- If the goal is unclear, make reasonable assumptions based on common patterns

Return the JSON now:"""

        for attempt in range(max_retries):
            if attempt == 0:
                prompt = base_prompt
            elif attempt == 1:
                prompt = base_prompt + "\n\nIMPORTANT: Return ONLY valid JSON with all required keys: data_models, api_endpoints, file_structure, shared_constants"
            else:
                # Last retry: provide schema template
                prompt = base_prompt + """

Use this exact structure:
{
  "data_models": [],
  "api_endpoints": [],
  "file_structure": [],
  "shared_constants": {}
}"""

            try:
                response = await self._call_llm(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=SYSTEM_PROMPT,
                    temperature=0.3,
                    max_tokens=4096,  # Increased from 2048 to allow more detailed contracts
                )

                # DEBUG: Print raw LLM response
                print(f"[Architect DEBUG] Attempt {attempt + 1}/{max_retries}")
                print(f"[Architect DEBUG] Raw LLM response: {repr(response)[:500]}")

                # Parse JSON from response
                contract = self._parse_json_response(response)
                
                # DEBUG: Print parsed contract
                print(f"[Architect DEBUG] Parsed contract: {contract}")
                
                if contract and self._has_required_keys(contract):
                    # DEBUG: Print successful contract
                    print(f"[Architect DEBUG] Contract has all required keys!")
                    print(f"[Architect DEBUG] data_models count: {len(contract.get('data_models', []))}")
                    print(f"[Architect DEBUG] api_endpoints count: {len(contract.get('api_endpoints', []))}")
                    print(f"[Architect DEBUG] file_structure count: {len(contract.get('file_structure', []))}")
                    return contract
                else:
                    print(f"[Architect DEBUG] Contract missing required keys or is None")

            except Exception as e:
                print(f"[Architect DEBUG] Exception during attempt {attempt + 1}: {e}")
                continue

        # Final fallback: minimal valid contract
        return {
            "data_models": [],
            "api_endpoints": [],
            "file_structure": [],
            "shared_constants": {},
        }

    def _has_required_keys(self, contract: dict) -> bool:
        """Check if contract has all 4 required top-level keys."""
        required_keys = {"data_models", "api_endpoints", "file_structure", "shared_constants"}
        return required_keys.issubset(contract.keys())

    def _validate_contract(self, contract: dict) -> list[str]:
        """
        Validate contract schema and return list of errors.

        Args:
            contract: Contract dictionary to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check required top-level keys
        required_keys = {"data_models", "api_endpoints", "file_structure", "shared_constants"}
        missing_keys = required_keys - set(contract.keys())
        if missing_keys:
            errors.append(f"Missing required keys: {missing_keys}")
            return errors  # Can't continue validation without keys

        # Validate data_models
        if not isinstance(contract["data_models"], list):
            errors.append("data_models must be a list")
        else:
            for i, model in enumerate(contract["data_models"]):
                if not isinstance(model, dict):
                    errors.append(f"data_models[{i}] must be a dict")
                    continue
                if "name" not in model or not isinstance(model["name"], str):
                    errors.append(f"data_models[{i}] missing 'name' (string)")
                if "fields" not in model or not isinstance(model["fields"], list):
                    errors.append(f"data_models[{i}] missing 'fields' (list)")
                if "description" not in model or not isinstance(model["description"], str):
                    errors.append(f"data_models[{i}] missing 'description' (string)")

        # Validate api_endpoints
        if not isinstance(contract["api_endpoints"], list):
            errors.append("api_endpoints must be a list")
        else:
            for i, endpoint in enumerate(contract["api_endpoints"]):
                if not isinstance(endpoint, dict):
                    errors.append(f"api_endpoints[{i}] must be a dict")
                    continue
                if "path" not in endpoint or not isinstance(endpoint["path"], str):
                    errors.append(f"api_endpoints[{i}] missing 'path' (string)")
                if "method" not in endpoint or not isinstance(endpoint["method"], str):
                    errors.append(f"api_endpoints[{i}] missing 'method' (string)")
                # Accept both dict and str for input_schema (e.g., "TodoCreate" or {"title": "str"})
                if "input_schema" not in endpoint or not isinstance(endpoint["input_schema"], (dict, str)):
                    errors.append(f"api_endpoints[{i}] missing 'input_schema' (dict or string)")
                # Accept both dict and str for output_schema (e.g., "Todo" or {"id": "int", "title": "str"})
                if "output_schema" not in endpoint or not isinstance(endpoint["output_schema"], (dict, str)):
                    errors.append(f"api_endpoints[{i}] missing 'output_schema' (dict or string)")

        # Validate file_structure
        if not isinstance(contract["file_structure"], list):
            errors.append("file_structure must be a list")
        else:
            for i, file in enumerate(contract["file_structure"]):
                if not isinstance(file, dict):
                    errors.append(f"file_structure[{i}] must be a dict")
                    continue
                if "path" not in file or not isinstance(file["path"], str):
                    errors.append(f"file_structure[{i}] missing 'path' (string)")
                if "responsibility" not in file or not isinstance(file["responsibility"], str):
                    errors.append(f"file_structure[{i}] missing 'responsibility' (string)")
                if "exports" not in file or not isinstance(file["exports"], list):
                    errors.append(f"file_structure[{i}] missing 'exports' (list)")

        # Validate shared_constants
        if not isinstance(contract["shared_constants"], dict):
            errors.append("shared_constants must be a dict")

        return errors
