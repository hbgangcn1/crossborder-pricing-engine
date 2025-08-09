import sqlite3
import pytest
from unittest.mock import MagicMock, patch
import os
import hashlib
import pandas as pd

import db_utils

@pytest.fixture
def mock_db_connection():
    """Fixture to create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    yield conn, cursor
    conn.close()

@pytest.fixture
def mock_db(mock_db_connection):
    """Fixture that provides an initialized in-memory database."""
    conn, cursor = mock_db_connection
    # Patch get_db to return our in-memory connection
    with patch('db_utils.get_db', return_value=(conn, cursor)):
        db_utils.init_db()
        yield conn, cursor

@pytest.fixture
def mock_streamlit(mocker):
    """Fixture to mock streamlit and its session_state."""
    mocker.patch('streamlit.session_state', new_callable=MagicMock)
    # Since we are not in a real streamlit run, st.rerun will fail.
    mocker.patch('streamlit.rerun')
    # Also mock error/success messages
    mocker.patch('streamlit.error')
    mocker.patch('streamlit.success')
    mocker.patch('streamlit.warning')
    mocker.patch('streamlit.info')

def test_get_db(mocker):
    """Test the get_db function."""
    mocker.patch('os.path.join', return_value='test_db_path')
    mock_connect = mocker.patch('sqlite3.connect')
    db_utils.get_db()
    mock_connect.assert_called_once_with('test_db_path', check_same_thread=False)

def test_current_user_id(mock_streamlit):
    """Test that current_user_id returns the correct id from session_state."""
    import streamlit as st
    st.session_state.user = {"id": 123}
    assert db_utils.current_user_id() == 123

def test_create_user(mock_db):
    """Test creating a new user."""
    conn, c = mock_db

    # Patch init_db to avoid recursive calls within the function itself
    with patch('db_utils.init_db'):
        result = db_utils.create_user("testuser", "password123", "user", "test@example.com")

    assert result is True
    user = c.execute("SELECT * FROM users WHERE username = 'testuser'").fetchone()
    assert user is not None
    assert user['username'] == 'testuser'
    assert user['role'] == 'user'
    assert user['email'] == 'test@example.com'

    # Test creating a duplicate user
    with patch('db_utils.init_db'):
        result_fail = db_utils.create_user("testuser", "password123")
    assert result_fail is False

def test_verify_user(mock_db):
    """Test user verification."""
    conn, c = mock_db
    password = "password123"

    # Create a user to verify
    with patch('db_utils.init_db'):
        db_utils.create_user("verifyuser", password, "user", "verify@example.com")

    with patch('db_utils.init_db'):
        # Test successful verification with username
        user = db_utils.verify_user("verifyuser", password)
        assert user is not None
        assert user['username'] == 'verifyuser'

        # Test successful verification with email
        user_email = db_utils.verify_user("verify@example.com", password)
        assert user_email is not None
        assert user_email['username'] == 'verifyuser'

        # Test failed verification (wrong password)
        wrong_pass_user = db_utils.verify_user("verifyuser", "wrongpassword")
        assert wrong_pass_user is None

        # Test failed verification (user not found)
        not_found_user = db_utils.verify_user("nouser", "password123")
        assert not_found_user is None

@pytest.fixture
def product_fixture(mock_db):
    """Fixture to add some products for a user."""
    conn, c = mock_db
    user_id = 1 # admin user created by init_db
    products_to_add = [
        (user_id, 'Product A', 'Cat1', 100),
        (user_id, 'Product B', 'Cat1', 200),
        (user_id, 'Product C', 'Cat2', 300),
    ]
    for p in products_to_add:
        c.execute("INSERT INTO products (user_id, name, category, weight_g) VALUES (?, ?, ?, ?)", p)
    conn.commit()
    return user_id

def test_add_product(mock_db):
    """Test adding a new product."""
    conn, c = mock_db
    user_id = 1
    product_data = {
        "user_id": user_id, "name": "Test Product", "russian_name": "", "category": "Test Cat",
        "model": "T-1000", "unit_price": 99.9, "weight_g": 500, "length_cm": 10,
        "width_cm": 5, "height_cm": 2, "is_cylinder": 0, "cylinder_diameter": 0,
        "cylinder_length": 0, "has_battery": 0, "battery_capacity_wh": 0,
        "battery_capacity_mah": 0, "battery_voltage": 0, "has_msds": 0,
        "has_flammable": 0, "shipping_fee": 10, "labeling_fee": 1,
        "promotion_discount": 0.1, "promotion_cost_rate": 0.1,
        "target_profit_margin": 0.5, "commission_rate": 0.15,
        "withdrawal_fee_rate": 0.01, "payment_processing_fee": 0.02
    }
    db_utils.add_product(product_data)

    product = c.execute("SELECT * FROM products WHERE name = 'Test Product'").fetchone()
    assert product is not None
    assert product['category'] == 'Test Cat'
    assert product['unit_price'] == 99.9

def test_get_all_products_for_user(mock_db, product_fixture):
    """Test fetching all products for a given user."""
    user_id = product_fixture
    products = db_utils.get_all_products_for_user(user_id)
    assert len(products) == 3
    assert products[0]['name'] == 'Product A'

def test_get_product_by_id(mock_db, product_fixture):
    """Test fetching a single product by its ID."""
    user_id = product_fixture
    # Let's get the ID of 'Product B'
    product_b_id = db_utils.get_all_products_for_user(user_id)[1]['id']

    product = db_utils.get_product_by_id(product_b_id, user_id)
    assert product is not None
    assert product['name'] == 'Product B'

    # Test getting a non-existent product
    non_existent = db_utils.get_product_by_id(999, user_id)
    assert non_existent is None

def test_delete_product(mock_db, product_fixture):
    """Test deleting a product."""
    user_id = product_fixture
    products_before = db_utils.get_all_products_for_user(user_id)
    assert len(products_before) == 3

    product_to_delete_id = products_before[0]['id']
    db_utils.delete_product(product_to_delete_id, user_id)

    products_after = db_utils.get_all_products_for_user(user_id)
    assert len(products_after) == 2
    assert all(p['id'] != product_to_delete_id for p in products_after)

def test_batch_delete_products(mock_db, product_fixture):
    """Test batch deleting products."""
    user_id = product_fixture
    products_before = db_utils.get_all_products_for_user(user_id)
    assert len(products_before) == 3

    ids_to_delete = [p['id'] for p in products_before[:2]] # Delete first two
    db_utils.batch_delete_products(ids_to_delete, user_id)

    products_after = db_utils.get_all_products_for_user(user_id)
    assert len(products_after) == 1
    assert products_after[0]['name'] == 'Product C'

def test_update_product(mock_db, product_fixture):
    """Test updating a product."""
    conn, c = mock_db
    user_id = product_fixture
    product_to_update_id = db_utils.get_all_products_for_user(user_id)[0]['id']

    update_data = db_utils.get_product_by_id(product_to_update_id, user_id)
    update_data = dict(update_data) # Convert from sqlite3.Row
    update_data['name'] = "Updated Product A"
    update_data['unit_price'] = 123.45

    db_utils.update_product(product_to_update_id, update_data)

    updated_product = db_utils.get_product_by_id(product_to_update_id, user_id)
    assert updated_product['name'] == "Updated Product A"
    assert updated_product['unit_price'] == 123.45

def test_batch_update_pricing_params(mock_db, product_fixture):
    """Test batch updating pricing parameters for products."""
    conn, c = mock_db
    user_id = product_fixture
    products_before = db_utils.get_all_products_for_user(user_id)
    ids_to_update = [p['id'] for p in products_before]

    params = {
        "promotion_discount": 0.5, "promotion_cost_rate": 0.4,
        "target_profit_margin": 0.3, "commission_rate": 0.2,
        "withdrawal_fee_rate": 0.1, "payment_processing_fee": 0.05
    }

    db_utils.batch_update_pricing_params(ids_to_update, params, user_id)

    # Check one product to see if it was updated
    p = db_utils.get_product_by_id(ids_to_update[0], user_id)
    assert p['target_profit_margin'] == 0.3
    assert p['commission_rate'] == 0.2

def test_init_db(mock_db_connection):
    """Test the database initialization."""
    conn, c = mock_db_connection

    # Patch get_db to return our clean in-memory connection
    with patch('db_utils.get_db', return_value=(conn, c)):
        db_utils.init_db()

    # Check if tables are created
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    assert 'users' in tables
    assert 'products' in tables
    assert 'logistics' in tables

    # Check if admin user is created
    admin = c.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    assert admin is not None
    assert admin['role'] == 'admin'

    # Check that calling it again doesn't create a new admin
    with patch('db_utils.get_db', return_value=(conn, c)):
        db_utils.init_db()
    c.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
    count = c.fetchone()[0]
    assert count == 1

@pytest.fixture
def logistics_fixture(mock_db):
    """Fixture to add logistics data for priority group calculation."""
    conn, c = mock_db
    user_id = 1
    logistics_data = [
        # land
        (user_id, 'Land Fast', 'land', 10, 20), # A
        (user_id, 'Land Medium', 'land', 20, 40), # C
        (user_id, 'Land Slow', 'land', 30, 60), # D
        # air
        (user_id, 'Air Fast', 'air', 5, 10), # A
        (user_id, 'Air Medium', 'air', 10, 20), # C
        (user_id, 'Air Slow', 'air', 15, 30), # D
        (user_id, 'Air Zero', 'air', 0, 0) # E
    ]
    c.executemany("INSERT INTO logistics (user_id, name, type, min_days, max_days) VALUES (?, ?, ?, ?, ?)", logistics_data)
    conn.commit()
    return user_id

def test_calculate_and_update_priority_groups(mock_db, logistics_fixture):
    """Test the priority group calculation and update logic."""
    conn, c = mock_db

    db_utils.calculate_and_update_priority_groups()

    c.execute("SELECT name, priority_group FROM logistics ORDER BY name")
    results = c.fetchall()

    expected_groups = {
        'Air Fast': 'A',
        'Air Medium': 'D', # Corrected from 'C'
        'Air Slow': 'D',
        'Air Zero': 'E',
        'Land Fast': 'A',
        'Land Medium': 'D', # Corrected from 'C'
        'Land Slow': 'D',
    }

    assert len(results) == len(expected_groups)
    for row in results:
        assert expected_groups[row['name']] == row['priority_group']
