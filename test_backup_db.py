import os
import sys
import sqlite3
import time
from unittest.mock import patch, MagicMock

import pytest

# Add the root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '.')))

import backup_db

@pytest.fixture

def temp_db_and_backup_dir(tmp_path):
    """Fixture to create a temporary database file and backup directory."""
    db_path = tmp_path / "pricing_system.db"
    # Create a dummy db file
    db_path.touch()

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Patch the functions to use the temp directory
    with patch('backup_db.Path') as mock_path:
        mock_path.return_value = db_path
        mock_path.exists.return_value = True
        with patch('backup_db.get_backup_dir', return_value=backup_dir):
            yield tmp_path, db_path, backup_dir

def test_create_backup_success(temp_db_and_backup_dir, mocker):
    """Test a successful backup creation."""
    tmp_path, db_path, backup_dir = temp_db_and_backup_dir

    mocker.patch('backup_db.setup_logging')
    # Mock the db validation part to avoid real db connection
    mocker.patch('sqlite3.connect')

    result = backup_db.create_backup()

    assert result is True
    # Check that a backup file was created
    backup_files = list(backup_dir.glob("*.db"))
    assert len(backup_files) == 1
    assert "pricing_system_backup" in backup_files[0].name

def test_create_backup_db_not_found(temp_db_and_backup_dir, mocker):
    """Test backup creation when the source database doesn't exist."""
    tmp_path, db_path, backup_dir = temp_db_and_backup_dir

    mocker.patch('backup_db.setup_logging')
    # Make the db path appear as not existing
    db_path.unlink()

    result = backup_db.create_backup()

    assert result is False
    assert len(list(backup_dir.glob("*.db"))) == 0

def test_create_backup_validation_fails(temp_db_and_backup_dir, mocker):
    """Test backup creation when database validation fails."""
    tmp_path, db_path, backup_dir = temp_db_and_backup_dir

    mocker.patch('backup_db.setup_logging')
    # Mock the db validation to raise an exception
    mocker.patch('sqlite3.connect', side_effect=sqlite3.DatabaseError("Validation failed"))

    result = backup_db.create_backup()

    assert result is False
    assert len(list(backup_dir.glob("*.db"))) == 0

def test_cleanup_old_backups(temp_db_and_backup_dir):
    """Test the cleanup logic for old backups."""
    tmp_path, db_path, backup_dir = temp_db_and_backup_dir

    # Create 10 dummy backup files with different timestamps
    for i in range(10):
        p = backup_dir / f"pricing_system_backup_2025010{i}.db"
        p.touch()
        # Set modification time to be different for each
        mod_time = time.time() - (10 - i) * 1000
        os.utime(p, (mod_time, mod_time))

    backup_db.cleanup_old_backups(backup_dir, MagicMock())

    # Should be 7 files left (the most recent ones)
    remaining_files = list(backup_dir.glob("*.db"))
    assert len(remaining_files) == 7

    # Check that the oldest files were deleted
    remaining_names = {f.name for f in remaining_files}
    assert "pricing_system_backup_20250100.db" not in remaining_names
    assert "pricing_system_backup_20250101.db" not in remaining_names
    assert "pricing_system_backup_20250102.db" not in remaining_names

def test_restore_backup_success(temp_db_and_backup_dir, mocker):
    """Test a successful database restore."""
    tmp_path, db_path, backup_dir = temp_db_and_backup_dir
    mocker.patch('backup_db.setup_logging')

    # Create a dummy backup file
    backup_file = backup_dir / "backup.db"
    backup_file.write_text("backup content")

    # Make sure the original db has different content
    db_path.write_text("original content")

    result = backup_db.restore_backup("backup.db")

    assert result is True
    # The main db should now have the content of the backup
    assert db_path.read_text() == "backup content"
    # A safety backup should have been created
    safety_backups = list(backup_dir.glob("pre_restore_backup_*.db"))
    assert len(safety_backups) == 1
    assert safety_backups[0].read_text() == "original content"

def test_restore_backup_not_found(temp_db_and_backup_dir, mocker):
    """Test restore when the backup file doesn't exist."""
    tmp_path, db_path, backup_dir = temp_db_and_backup_dir
    mocker.patch('backup_db.setup_logging')

    result = backup_db.restore_backup("non_existent_backup.db")

    assert result is False

def test_list_backups(temp_db_and_backup_dir, mocker):
    """Test listing available backups."""
    tmp_path, db_path, backup_dir = temp_db_and_backup_dir
    mock_logger = MagicMock()
    mocker.patch('backup_db.setup_logging', return_value=mock_logger)

    # Create some dummy backup files
    (backup_dir / "pricing_system_backup_2.db").touch()
    (backup_dir / "pricing_system_backup_1.db").touch()

    backup_db.list_backups()

    # Check that the logger was called with info about the files
    # The logger is called multiple times, we check for the file names
    log_calls = [str(call) for call in mock_logger.info.call_args_list]
    assert any("pricing_system_backup_1.db" in call for call in log_calls)
    assert any("pricing_system_backup_2.db" in call for call in log_calls)

@patch('backup_db.create_backup')
@patch('backup_db.list_backups')
@patch('backup_db.restore_backup')

def test_main_cli(mock_restore, mock_list, mock_create, mocker):
    """Test the main CLI entry point."""

    # Test 'backup' command
    with patch('sys.argv', ['backup_db.py', 'backup']):
        with pytest.raises(SystemExit):
            backup_db.main()
    mock_create.assert_called_once()

    # Test 'list' command
    with patch('sys.argv', ['backup_db.py', 'list']):
        with pytest.raises(SystemExit):
            backup_db.main()
    mock_list.assert_called_once()

    # Test 'restore' command
    with patch('sys.argv', ['backup_db.py', 'restore', 'my_backup.db']):
        with pytest.raises(SystemExit):
            backup_db.main()
    mock_restore.assert_called_once_with('my_backup.db')

    # Test no command (should show usage)
    mock_create.reset_mock()
    with patch('sys.argv', ['backup_db.py']):
        with pytest.raises(SystemExit):
            backup_db.main()
    # No command should show usage, not call create_backup
    mock_create.assert_not_called()
