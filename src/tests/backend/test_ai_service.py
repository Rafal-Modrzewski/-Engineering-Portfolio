import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

# Import the deterministic_ai_service 
from src.backend.deterministic_ai_service import AIService, BusinessLogicError, Campaign, CAMPAIGN_STATES
# --- FIXTURES ---

@pytest.fixture
def mock_db_session():
    """Mocks the SQLAlchemy AsyncSession"""
    session = AsyncMock(spec=AsyncSession)
    # Mocking the execute().scalar_one_or_none() chain
    execute_result = MagicMock()
    session.execute.return_value = execute_result
    return session, execute_result

@pytest.fixture
def ai_service():
    return AIService()

@pytest.fixture
def valid_uuids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

# --- TESTS ---

@pytest.mark.asyncio
async def test_guardrail_valid_flow(ai_service, mock_db_session, valid_uuids):
    """
    Happy Path: 
    1. Campaign exists.
    2. Status is 'ideas_approved'.
    3. Action 'generate-content' is allowed in 'ideas_approved'.
    """
    session, result_mock = mock_db_session
    campaign_id, user_id, bus_id = valid_uuids
    
    # Setup Mock Campaign
    mock_campaign = Campaign(id=campaign_id, business_id=bus_id, status='ideas_approved')
    
    # 1. Mock the decorator query (execute -> scalar_one_or_none)
    result_mock.scalar_one_or_none.return_value = mock_campaign
    
    # 2. Mock the service method query (db.get)
    session.get.return_value = mock_campaign

    # Run
    result = await ai_service.generate_content(
        session, campaign_id, user_id, {"topic": "AI"}
    )

    # Assert
    assert result['status'] == 'content_generated'
    assert "headline" in result['content']
    # Verify DB was queried
    assert session.execute.called

@pytest.mark.asyncio
async def test_guardrail_invalid_state(ai_service, mock_db_session, valid_uuids):
    """
    State Machine Check:
    Campaign is in 'draft', but we try to call 'generate_content'.
    Should fail because 'draft' -> 'generate-content' is invalid transition.
    """
    session, result_mock = mock_db_session
    campaign_id, user_id, bus_id = valid_uuids
    
    # Setup Campaign in WRONG state
    mock_campaign = Campaign(id=campaign_id, business_id=bus_id, status='draft')
    result_mock.scalar_one_or_none.return_value = mock_campaign

    with pytest.raises(BusinessLogicError) as exc:
        await ai_service.generate_content(
            session, campaign_id, user_id, {}
        )
    
    assert "Invalid state 'draft'" in str(exc.value)

@pytest.mark.asyncio
async def test_guardrail_invalid_action_logic(ai_service, mock_db_session, valid_uuids):
    """
    Action Logic Check:
    We force a status where the function call doesn't make sense.
    Technically 'generate_content' expects 'ideas_approved'.
    If we manually passed 'ideas_approved' but the logic table said 'generate-content'
    wasn't allowed, it should fail.
    """
    session, result_mock = mock_db_session
    campaign_id, user_id, bus_id = valid_uuids
    
    # Let's pretend we are in 'ideas_approved'
    # But let's temporarily tamper with the global config to prove the logic works
    # (Simulating a misconfigured state machine)
    original_states = CAMPAIGN_STATES.copy()
    CAMPAIGN_STATES['ideas_approved'] = ['some-other-action'] # Removed 'generate-content'
    
    try:
        mock_campaign = Campaign(id=campaign_id, business_id=bus_id, status='ideas_approved')
        result_mock.scalar_one_or_none.return_value = mock_campaign

        with pytest.raises(BusinessLogicError) as exc:
            await ai_service.generate_content(session, campaign_id, user_id, {})
        
        assert "Action 'generate-content' not allowed" in str(exc.value)
    finally:
        # Restore state
        CAMPAIGN_STATES.update(original_states)

def test_robust_json_parsing_markdown(ai_service):
    """Test parsing of LLM markdown blocks"""
    
    # Case 1: Standard Markdown
    raw_llm = '```json\n{"headline": "Success", "body": "Works"}\n```'
    parsed = ai_service._robust_json_parse(raw_llm)
    assert parsed['headline'] == "Success"

    # Case 2: Trailing commas (JSON5 feature)
    raw_llm_lazy = '{"headline": "Success", "body": "Works",}' 
    parsed = ai_service._robust_json_parse(raw_llm_lazy)
    assert parsed['headline'] == "Success"

    # Case 3: Messy text before/after (Common LLM chatter)
    raw_llm_messy = 'Here is your JSON:\n```json\n{"headline": "Success", "body": "Works"}\n```\nHope you like it!'
    parsed = ai_service._robust_json_parse(raw_llm_messy)
    assert parsed['headline'] == "Success"

def test_robust_json_parsing_failure(ai_service):
    """Test absolute garbage input"""
    raw_garbage = "I cannot generate that for you."
    
    with pytest.raises(BusinessLogicError) as exc:
        ai_service._robust_json_parse(raw_garbage)
    
    assert "LLM Output Parsing Failed" in str(exc.value)
