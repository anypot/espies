"""Integration tests for main module workflow."""


class TestMainWorkflow:
    """Tests for main.py orchestration logic."""

    def test_create_checkpoint_used_in_all_paths(self):
        """Verify all checkpoint creation paths use the helper method."""
        import inspect
        from espies.main import main, _run_iteration

        main_source = inspect.getsource(main)
        run_iteration_source = inspect.getsource(_run_iteration)

        # Check that CheckpointData constructor is not called directly
        assert 'CheckpointData(' not in main_source, "CheckpointData should be created via create_checkpoint helper"

        # Check that create_checkpoint is called
        assert 'create_checkpoint' in run_iteration_source

    def test_commit_message_from_review_result(self):
        """Verify commit uses reviewer-provided commit message."""
        import inspect
        from espies.main import _handle_approved_result

        source = inspect.getsource(_handle_approved_result)

        # Check that commit_msg variable is extracted from result.commit_message
        assert 'result.commit_message' in source
        assert 'commit_msg = result.commit_message' in source


class TestDryRunHandling:
    """Tests for dry-run mode in main workflow."""

    def test_dry_run_logs_commit_message(self):
        """Dry-run mode includes commit message in logs."""
        import inspect
        from espies.main import _handle_approved_result

        source = inspect.getsource(_handle_approved_result)

        # Verify dry-run logs the commit message
        assert 'dry_run=True, message=commit_msg' in source