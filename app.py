from flask import Flask, request, jsonify, make_response  
import json
import validators
import re
import csv
import io


app = Flask(__name__)

mobile_regex = re.compile(r'^\d{10}$')
users = {}
expenses = {}
expense_id = 1
user_id = 1
user_balances = {}


@app.route('/add', methods=['POST'])
def add_user():
    global user_id
    data = request.get_json()

    try:
        name = data.get('name')
        email = data.get('email')
        mobile = data.get('mobile')

        errors = {}
        if not name:
            errors['name'] = 'Name is required'
        if not email:
            errors['email'] = 'Email is required'
        elif not validators.email(email):
            errors['email'] = 'Invalid email format'
        if not mobile:
            errors['mobile'] = 'Mobile is required'
        elif not mobile_regex.match(mobile):
            errors['mobile'] = 'Invalid mobile format'
        if errors:
            return jsonify({'errors': errors}), 400

        user = {'id': user_id, 'name': name, 'email': email, 'mobile': mobile}
        users[user_id] = user
        user_id += 1

        return jsonify(user), 201  # Return the created user

    except Exception as e:
        return jsonify({'error': 'Failed to add user'}), 500


@app.route('/edit/<int:id>', methods=['POST'])
def edit_user(id):
    user = users.get(id)
    name = request.form['name']
    email = request.form['email']
    mobile = request.form['mobile']
    errors = {}
    if not name:
        errors['name'] = 'Name is required'
    if not email:
        errors['email'] = 'Email is required'
    elif not validators.email(email):
        errors['email'] = 'Invalid email format'
    if not mobile:
        errors['mobile'] = 'Mobile is required'
    elif not mobile_regex.match(mobile):
        errors['mobile'] = 'Invalid mobile format'
    if errors:
        return jsonify({'errors': errors}), 400
    
    users[id]['name'] = name
    users[id]['email'] = email
    users[id]['mobile'] = mobile
    return jsonify(user)


@app.route('/delete/<int:id>')
def delete_user(id):
    if id in users:
        del users[id]
    else:
        return jsonify({'errors': 'User does not exist'}), 400

# List users route
@app.route('/users')
def list_users():
    return users


@app.route('/add_expense', methods=['POST'])
def add_expense():
    global expense_id
    data = request.get_json()

    try:
        if not all(key in data for key in ('payer_id', 'amount', 'participants', 'splits')): 
            raise ValueError("Missing required fields")

        payer_id = data['payer_id']
        amount = float(data['amount'])
        participants = data['participants']  
        splits = data['splits']

        # Check if payer and participants exist
        if payer_id not in users:
            raise ValueError("Invalid payer ID")
        for participant_id in participants:
            if participant_id not in users:
                raise ValueError(f"Invalid participant ID: {participant_id}")

        if len(participants) != len(splits):
            raise ValueError("Number of participants and splits must match")

        # Split calculation
        split_amounts = calculate_splits(amount, splits)

        # Create expense record
        expense = {
            'id': expense_id,
            'payer_id': payer_id,  # Store payer ID
            'amount': amount,
            'participants': participants,  # Store participant IDs
            'splits': splits,
            'split_amounts': split_amounts
        }
        expenses[expense_id] = expense
        expense_id += 1

        return jsonify(expense), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Failed to add expense'}), 500

def calculate_splits(amount, splits):
    split_method = splits[0]['method'] if splits else 'equal'  # Default to equal if no splits provided
    split_amounts = []

    if split_method == 'exact':
        if sum(split['amount'] for split in splits) != amount:
            raise ValueError("Exact split amounts must add up to the total amount")
        split_amounts = [split['amount'] for split in splits]

    elif split_method == 'percentage':
        if sum(split['percentage'] for split in splits) != 100:
            raise ValueError("Percentages must add up to 100")
        split_amounts = [(split['percentage'] / 100) * amount for split in splits]

    elif split_method == 'equal':
        split_amount = amount / len(splits)
        split_amounts = [split_amount] * len(splits)

    else:
        raise ValueError("Invalid split method")

    return split_amounts

@app.route('/balance_sheet', methods=['GET'])
def get_balance_sheet():
    try:
        balances = {}
        for expense in expenses.values():
            payer_id = expense['payer_id']
            split_amounts = expense['split_amounts']
            participants = expense['participants']

            # Credit the payer
            balances[payer_id] += expense['amount']

            # Debit the participants
            for i, participant_id in enumerate(participants):
                balances[participant_id] -= split_amounts[i]

        # Format the output
        balance_sheet = [
            {'user_id': user_id, 'name': users[user_id]['name'], 'balance': balance}
            for user_id, balance in balances.items()
        ]

        return jsonify(balance_sheet), 200

    except Exception as e:
        return jsonify({'error': 'Failed to generate balance sheet'}), 500

@app.route('/expenses/<int:user_id>', methods=['GET'])
def get_user_expenses(user_id):
    try:
        if user_id not in users:
            raise ValueError("Invalid user ID")

        user_expenses = []
        for expense_id, expense in expenses.items():
            if user_id in expense['participants']:
                # Include relevant expense details
                expense_info = {
                    'expense_id': expense_id,
                    'payer': users[expense['payer_id']]['name'],  # Get payer name
                    'amount': expense['amount'],
                    'split_amount': expense['split_amounts'][expense['participants'].index(user_id)],
                }
                user_expenses.append(expense_info)

        return jsonify(user_expenses), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Failed to retrieve expenses'}), 500

@app.route('/download_balance_sheet')
def download_balance_sheet():
    try:
        # Calculate balances (same logic as in /balance_sheet)
        balances = {}
        for expense in expenses.values():
            payer_id = expense['payer_id']
            split_amounts = expense['split_amounts']
            participants = expense['participants']

            balances[payer_id] += expense['amount']
            for i, participant_id in enumerate(participants):
                balances[participant_id] -= split_amounts[i]

        # Create a CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['User ID', 'Name', 'Balance'])  # Write the header row
        for user_id, balance in balances.items():
            writer.writerow([user_id, users[user_id]['name'], balance])  # Write each user's balance

        # Create a response object for downloading the CSV file
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=balance_sheet.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    except Exception as e:
        return jsonify({'error': 'Failed to generate balance sheet'}), 500


if __name__ == '__main__':
    app.run(port=5001,debug=True)
