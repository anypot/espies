"""Integration tests for agent module."""

from espies.agent import ReviewResult, parse_reviewer_response


class TestReviewResult:
    """Tests for ReviewResult named tuple."""

    def test_review_result_with_all_fields(self):
        """ReviewResult accepts decision, explanation, and commit_message."""
        result = ReviewResult(
            decision="APPROVE",
            explanation="Code looks good",
            commit_message="Fix authentication bug"
        )
        assert result.decision == "APPROVE"
        assert result.explanation == "Code looks good"
        assert result.commit_message == "Fix authentication bug"

    def test_review_result_defaults(self):
        """ReviewResult has sensible defaults for explanation and commit_message."""
        result = ReviewResult(decision="REJECT")
        assert result.decision == "REJECT"
        assert result.explanation == ""
        assert result.commit_message == ""


class TestParseReviewerResponse:
    """Tests for parse_reviewer_response function."""

    def test_parses_approve_with_commit_message(self):
        """JSON with commit_message is parsed correctly."""
        response = '{"decision": "APPROVE", "explanation": "", "commit_message": "Add new feature"}'
        result = parse_reviewer_response(response)
        assert result.decision == "APPROVE"
        assert result.commit_message == "Add new feature"

    def test_parses_approve_without_commit_message_backward_compat(self):
        """JSON without commit_message uses empty default (backward compat)."""
        response = '{"decision": "APPROVE", "explanation": ""}'
        result = parse_reviewer_response(response)
        assert result.decision == "APPROVE"
        assert result.commit_message == ""

    def test_parses_reject_with_explanation(self):
        """REJECT decision with explanation is parsed correctly."""
        response = '{"decision": "REJECT", "explanation": "Test failure", "commit_message": ""}'
        result = parse_reviewer_response(response)
        assert result.decision == "REJECT"
        assert result.explanation == "Test failure"

    def test_parses_plain_text_approve(self):
        """Legacy plain text APPROVE is handled."""
        result = parse_reviewer_response("APPROVE")
        assert result.decision == "APPROVE"

    def test_parses_plain_text_reject_with_explanation(self):
        """Legacy plain text REJECT with explanation is handled."""
        result = parse_reviewer_response("REJECT Insufficient tests")
        assert result.decision == "REJECT"
        assert result.explanation == "Insufficient tests"

    def test_handles_invalid_json_gracefully(self):
        """Invalid JSON falls back to plain text parsing."""
        result = parse_reviewer_response("Not JSON but APPROVE")
        assert result.decision == "REJECT"
        assert "Could not parse" in result.explanation

    def test_handles_invalid_decision(self):
        """Invalid decision value results in fallback parsing and REJECT."""
        response = '{"decision": "MAYBE", "explanation": ""}'
        result = parse_reviewer_response(response)
        assert result.decision == "REJECT"
        # Falls through to text parsing since "MAYBE" is not valid