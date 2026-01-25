import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime

# Import business logic functions and exceptions
# Ensure 'business_logic.py' is in the root directory or PYTHONPATH
from business_logic import (
    handle_user_request,
    start_campaign,
    require_valid_campaign,
    BusinessLogicError
)

# --- FIXTURES ---

@pytest.fixture
def mock_db():
    """
    Creates a mock database session mimicking SQLAlchemy AsyncSession.
    """
    session = AsyncMock()
    return session

@pytest.fixture
def mock_user_context():
    """Provides a standard user/campaign context for tests."""
    return {
        "user_id": uuid4(),
        "business_id": uuid4(),
        "campaign_id": uuid4()
    }

# --- DECORATOR TESTS (State Machine) ---

@pytest.mark.asyncio
async def test_require_valid_campaign_success(mock_db):
    """
    Verifies that the decorator allows execution when the campaign status matches expected state.
    """
    # 1. Setup
    campaign_id = uuid4()
    user_id = uuid4()
    
    # Mock Campaign and User objects returned by DB
    mock_campaign = MagicMock()
    mock_campaign.status = 'draft'
    mock_campaign.business_id = uuid4()
    
    mock_user = MagicMock()
    mock_user.id = user_id
    
    # Simulate DB query returning (Campaign, User)
    mock_db.execute.return_value.first.return_value = (mock_campaign, mock_user)

    # 2. Define protected function
    # Expects 'draft' state, implicit action 'start'
    @require_valid_campaign(expected_status=['draft'])
    async def start(db, campaign_id, user_id, **kwargs):
        return "Success"

    # 3. Execute
    result = await start(mock_db, campaign_id, user_id)
    
    # 4. Assert
    assert result == "Success"

@pytest.mark.asyncio
async def test_require_valid_campaign_wrong_state(mock_db):
    """
    Verifies that BusinessLogicError is raised when campaign status is invalid for the action.
    """
    campaign_id = uuid4()
    user_id = uuid4()
    
    mock_campaign = MagicMock()
    mock_campaign.status = 'draft' # Actual status
    
    mock_db.execute.return_value.first.return_value = (mock_campaign, MagicMock())

    # Function requires 'content_generated', but we are in 'draft'
    @require_valid_campaign(expected_status=['content_generated'])
    async def approve_content(db, campaign_id, user_id, **kwargs):
        return "Should not happen"

    # Expect BusinessLogicError
    with pytest.raises(BusinessLogicError) as exc_info:
        await approve_content(mock_db, campaign_id, user_id, action="approve_content")
    
    assert "Invalid campaign state" in str(exc_info.value.message)

@pytest.mark.asyncio
async def test_require_valid_campaign_not_found(mock_db):
    """
    Verifies behavior when the campaign does not exist in the database.
    """
    # Simulate DB returning None
    mock_db.execute.return_value.first.return_value = None

    @require_valid_campaign(['draft'])
    async def dummy_func(db, campaign_id, user_id, **kwargs):
        pass

    with pytest.raises(BusinessLogicError) as exc_info:
        await dummy_func(mock_db, uuid4(), uuid4())

    assert "Campaign not found" in str(exc_info.value.message)

# --- BUSINESS LOGIC FLOW TESTS ---

@pytest.mark.asyncio
async def test_handle_user_request_unknown_action(mock_db, mock_user_context):
    """
    Ensures the router raises an error for unrecognized actions.
    """
    with pytest.raises(BusinessLogicError) as exc_info:
        await handle_user_request(
            db=mock_db,
            user_id=mock_user_context['user_id'],
            business_id=mock_user_context['business_id'],
            action="unknown_action_xyz",
            user_input={}
        )
    
    assert "Unknown action" in str(exc_info.value) or "Unexpected error" in str(exc_info.value)

@pytest.mark.asyncio
async def test_start_campaign_flow(mock_db, mock_user_context):
    """
    Tests the full 'start_campaign' flow:
    1. Calls AI interface for ideas.
    2. Persists new campaign to DB.
    """
    user_id = mock_user_context['user_id']
    business_id = mock_user_context['business_id']
    user_input = {"topic": "AI Marketing Strategy"}

    # Mock dependencies: AI Interface and internal create/update helper
    with patch('business_logic.ai_interface') as mock_ai, \
         patch('business_logic.create_or_update_campaign') as mock_create:
        
        # 1. Configure AI Mock
        mock_ai.manage_ai_session.return_value = {
            "data": {
                "campaign_ideas": ["Strategy A", "Strategy B"],
                "error": None
            }
        }

        # 2. Configure DB Helper Mock
        # Must return (Campaign, CampaignVersion) tuple
        mock_campaign_obj = MagicMock()
        mock_campaign_obj.id = uuid4()
        mock_campaign_obj.status = 'ideas_generated'
        
        mock_version_obj = MagicMock()
        mock_version_obj.id = uuid4()

        mock_create.return_value = (mock_campaign_obj, mock_version_obj)
