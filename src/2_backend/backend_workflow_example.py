# src/2_backend/backend_workflow_example.py
#
# My Engineering Philosophy: Build for Velocity and Trust
#
# For a startup to succeed, engineering needs to be a force multiplier.
# My goal is to build resilient systems that allow a team to move fast with confidence.
# This file is a real-world example of how I create architectural "guardrails" that
# protect the core logic, enabling rapid feature development without sacrificing stability.

from typing import Dict, Any, Optional, List
from uuid import UUID
from functools import wraps
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# (Assume models and services are imported for this example)
# from Database.models import Campaign, User
# from process_with_ai.ai_interface import ai_interface

# ---
# 1. The Building Blocks: State & Custom Errors
# ---

CAMPAIGN_STATES = {
    'draft': ['start', 'refine-ideas'],
    'ideas_generated': ['approve-ideas', 'refine-ideas'],
    'ideas_approved': ['generate-content'],
    'content_generated': ['approve-content', 'refine-content'],
    'content_approved': ['complete']
}

class BusinessLogicError(Exception):
    """
    My custom exception for domain errors. It includes a `details` dictionary,
    so the API layer can provide rich, structured error responses to the client,
    which is crucial for good frontend development and debugging.
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

# ---
# 2. A Decorator for Clarity and Safety
# ---
# The Challenge: A campaign workflow is a state machine. The business rules for what can
# happen when (e.g., 'approve_content' requires 'ideas_approved') can get scattered
# across the codebase, making it slow to change and easy to break.
#
# My Solution: This decorator. It centralizes all workflow rules into one clear,
# declarative structure. This unleashes development speed because the logic for each
# step becomes simple, and the system becomes safer and almost self-documenting.

def require_valid_campaign(expected_status: List[str]):
    """
    This decorator proves the user is authorized and the campaign is in a valid
    state BEFORE a single line of business logic runs.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(db: AsyncSession, campaign_id: UUID, user_id: UUID, *args, **kwargs):
            # One efficient query to find the campaign AND verify user ownership.
            result = await db.execute(
                select(Campaign)
                .join(User, User.business_id == Campaign.business_id)
                .where(Campaign.id == campaign_id, User.id == user_id)
            )
            campaign = result.scalar_one_or_none()

            if not campaign:
                raise BusinessLogicError(
                    message="Campaign not found or user not authorized",
                    details={"campaign_id": str(campaign_id)}
                )

            action = func.__name__.replace('_', '-')

            # Check the rules defined in our CAMPAIGN_STATES map.
            if campaign.status not in expected_status:
                raise BusinessLogicError(
                    message="Invalid campaign state for this operation.",
                    details={"current_state": campaign.status, "expected_states": expected_status}
                )

            allowed_actions = CAMPAIGN_STATES.get(campaign.status, [])
            if action not in allowed_actions:
                raise BusinessLogicError(
                    message="Invalid action for the campaign's current state.",
                    details={"current_state": campaign.status, "action": action, "allowed_actions": allowed_actions}
                )

            return await func(db, campaign_id, user_id, *args, **kwargs)
        return wrapper
    return decorator

# ---
# 3. The Central Router
# ---
# This is the central router. It maps a simple string `action` from the API
# to the correct, decorator-protected business logic function. This pattern provides
# a predictable and scalable blueprint for the application's core logic, ensuring
# that adding new features is always a clean and straightforward process.

async def handle_campaign_action(
    db: AsyncSession,
    user_id: UUID,
    action: str,
    campaign_id: Optional[UUID] = None,
    **kwargs
) -> Dict[str, Any]:
    """Routes an incoming request to the correct handler."""

    action_handlers = {
        "start": start_campaign,
        "refine_ideas": refine_ideas,
        "approve_ideas": approve_ideas,
        "generate_content": generate_content,
        # ... other actions
    }

    handler = action_handlers.get(action)
    if not handler:
        raise BusinessLogicError(f"Unknown action: {action}")

    # The handler itself is protected by the @require_valid_campaign decorator. See line 129. 
    return await handler(db=db, user_id=user_id, campaign_id=campaign_id, **kwargs)

# ---
# 4. Function Example for the Business Logic
# ---

# This is the result of the architecture above. With the guardrails in place, the
# business logic is clean, focused, and free of boilerplate. It's concerned only
# with its specific task—creating value—confident that the system's integrity
# is already guaranteed.

@require_valid_campaign(['ideas_approved'])
async def generate_content(
    db: AsyncSession,
    user_id: UUID,
    campaign_id: UUID,
    user_input: Dict[str, Any],
    **kwargs # To absorb any other potential args from the router
) -> Dict[str, Any]:
    """
    Generates campaign content using an AI service. This function focuses purely on
    orchestration, confident that the decorator has already handled validation.
    """
    campaign = await db.get(Campaign, campaign_id)

    # 1. Call the AI service via a dedicated, isolated interface.
    ai_response = await ai_interface.manage_ai_session(
        db, user_id, campaign.business_id, "generate_content",
        campaign_id=campaign_id, user_input=user_input
    )

    # 2. Perform robust error handling on the AI's response.
    if isinstance(ai_response.get('data'), dict) and ai_response['data'].get('error'):
        ai_error_message = ai_response['data']['error']
        raise BusinessLogicError(
            message=f"AI content generation failed: {ai_error_message}",
            details={"campaign_id": str(campaign_id)}
        )
    campaign_content = ai_response.get('data', {}).get("generated_content", [])
    if not campaign_content:
        raise BusinessLogicError("AI returned empty content unexpectedly.")

    # 3. Persist the new state by calling a versioning helper.
    # (Implementation of create_or_update_campaign omitted for brevity).
    _campaign, new_version = await create_or_update_campaign(
        db=db, user_id=user_id, campaign_id=campaign_id, content=campaign_content, status='content_generated'
    )

    # 4. Return a clean, structured response for the API layer.
    return {
        "campaign_id": str(campaign_id),
        "content": campaign_content,
        "version_id": str(new_version.id)
    }
