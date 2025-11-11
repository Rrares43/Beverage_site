import os
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for

from db import Database
#test comment
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_in_prod")
database = Database()
STATUSES = ['pending', 'processing', 'shipped', 'completed', 'cancelled']


@app.route('/')
def products_page():
    return render_template('products.html')


@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    cust = database.get_customer_by_username(session['user'])
    return render_template('profile.html', customer=cust)


@app.route('/orders')
def orders():
    if 'user' not in session:
        return redirect(url_for('login'))
    cid = database.get_customer_id(session['user'])
    raw = database.get_orders_by_customer(cid)
    for o in raw:
        o['qty'] = database.get_order_quantity(o['id_order'])
    return render_template('orders.html', orders=raw)


@app.route('/employees')
def employees():
    if 'employee' not in session:
        return redirect(url_for('employee_login'))
    dept = session.get('employee_dept')
    if dept == 'achizitii':
        return redirect(url_for('employees_achizitii'))
    if dept == 'sales':
        return redirect(url_for('employees_vanzari'))
    if dept == 'productie':
        return redirect(url_for('employees_productie'))
    return redirect(url_for('employee_login'))


@app.route('/employees/achizitii')
def employees_achizitii():
    if session.get('employee_dept') != 'achizitii':
        return redirect(url_for('employee_login'))
    return render_template('employees_achizitii.html')


@app.route('/employees/achizitii/orders')
def employees_achizitii_orders():
    if session.get('employee_dept') != 'achizitii':
        return redirect(url_for('employee_login'))
    return render_template('employees_achizitii_orders.html')


@app.route('/employees/achizitii/order/<int:order_id>')
def achizitii_order_detail(order_id: int):
    if session.get('employee_dept') != 'achizitii':
        return redirect(url_for('employee_login'))
    eid = database.get_employee_id(session['employee'])
    order = database.get_partner_order(order_id, eid)
    if not order:
        return "Order not found or not assigned to you", 404
    items = database.get_partner_order_items(order_id)
    partner = database._fetchone_scalar(
        "SELECT name FROM partners WHERE id_partner=%s",
        (order['id_partner'],))
    order['date_fmt'] = order['data'].strftime('%Y-%m-%d %H:%M')
    return render_template('employees_achizitii_order.html', order=order, items=items, partner=partner)


@app.route('/employees/vanzari')
def employees_vanzari():
    if session.get('employee_dept') != 'sales':
        return redirect(url_for('employee_login'))
    return render_template('employees_vanzari.html')


@app.route('/employees/vanzari/order/<int:order_id>', methods=['GET', 'POST'])
def employee_order_detail(order_id: int):
    if session.get('employee_dept') != 'sales':
        return redirect(url_for('employee_login'))
    emp_user = session['employee']
    if request.method == 'POST':
        new_status = request.form.get('status')
        database.update_order_status(emp_user, order_id, new_status)
    emp_id = database.get_employee_id(emp_user)
    order = None
    for o in database.get_orders_by_employee(emp_id):
        if o['id_order'] == order_id:
            order = o
            break
    if not order:
        return "Order not found or not assigned to you", 404
    items = database.get_order_items(order_id)
    order['qty'] = sum(i['quantity'] for i in items)
    customer = database.get_customer_by_id(order['id_client'])
    return render_template(
        'employees_vanzari_order.html',
        order=order,
        items=items,
        customer=customer,
        statuses=STATUSES
    )


@app.route('/employees/productie')
def employees_productie():
    if session.get('employee_dept') != 'productie':
        return redirect(url_for('employee_login'))
    return render_template('employees_productie.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        uname = request.form['username'].strip().lower()
        pwd = request.form['password']
        if database.verify_customer(uname, pwd):
            session.clear()
            session['user'] = uname
            session.pop('employee', None)
            session.pop('employee_dept', None)
            return redirect(url_for('products_page'))
        error = 'Date invalide'
    return render_template('login.html', error=error)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        data = request.form
        username = data['username'].strip().lower()
        res = database.create_customer(
            data['name'], data['surname'], username, data['password'],
            data['email'], data.get('address', ''), data.get('phone', '')
        )
        if res.get('success'):
            session.clear();
            session['user'] = username
            return redirect(url_for('products_page'))
        error = res.get('error')
    return render_template('signup.html', error=error)


@app.route('/employee_login', methods=['GET', 'POST'])
def employee_login():
    error = None
    if request.method == 'POST':
        uname = request.form['username'].strip().lower()
        pwd = request.form['password']
        if database.verify_employee(uname, pwd):
            session.clear()
            emp = database.get_employee_by_username(uname)
            session.update({'employee': uname, 'employee_dept': emp['department']})
            session.pop('user', None)
            return redirect(url_for('employees'))
        error = 'Date invalide'
    return render_template('employee_login.html', error=error)


@app.route('/partner_login', methods=['GET', 'POST'])
def partner_login():
    error = None
    if request.method == 'POST':
        uname = request.form['username'].strip().lower()
        pwd = request.form['password']
        if database.verify_partner(uname, pwd):
            session.clear()
            session['partner'] = uname
            return redirect(url_for('partners_page'))
        error = 'Date invalide'
    return render_template('partner_login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('products_page'))


@app.route('/api/products')
def api_products():
    prods = database.get_stock()
    return (jsonify(prods), 200) if prods else (jsonify({'error': 'No products'}), 404)


@app.route('/api/stock')
def api_stock():
    final_only = request.args.get('final_only', '1') != '0'
    rows = database.get_stock(final_only=final_only)
    return (jsonify(rows), 200) if rows else (jsonify({'error': 'No products'}), 404)


@app.route('/api/achizitii/stock')
def api_achizitii_stock():
    if session.get('employee_dept') != 'achizitii':
        return jsonify({'error': 'Not authorized'}), 403
    rows = database.get_cheapest_partner_offer()
    raws = [
        r for r in rows
        if r['type'] != 'final' and r['partner_price'] is not None
    ]
    return jsonify(raws)


@app.route('/api/achizitii/place_order', methods=['POST'])
def api_achizitii_place_order():
    if session.get('employee_dept') != 'achizitii':
        return jsonify({'error': 'Not authorized'}), 403
    items = (request.get_json() or {}).get('items', [])
    emp_id = database.get_employee_id(session['employee'])
    res = database.create_procurement_orders(emp_id, items)
    return (jsonify(res), 200 if res.get('success') else 400)


@app.route('/api/achizitii/my_orders')
def api_achizitii_my_orders():
    if session.get('employee_dept') != 'achizitii':
        return jsonify({'error': 'Not authorized'}), 403
    eid = database.get_employee_id(session['employee'])
    rows = database.get_partner_orders()
    out = []
    for o in rows:
        if o['id_employee'] != eid:
            continue
        o['date_fmt'] = o['data'].strftime('%Y-%m-%d %H:%M')
        o['partner'] = database._fetchone_scalar(
            "SELECT name FROM partners WHERE id_partner=%s",
            (o['id_partner'],))
        out.append(o)
    return jsonify(out)


@app.route('/api/place_order', methods=['POST'])
def api_place_order():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 403
    items = (request.get_json() or {}).get('items', [])
    res = database.place_order(database.get_customer_id(session['user']), items)
    return (jsonify(res), 200 if res.get('success') else 400)


@app.route('/partners')
def partners_page():
    if 'partner' not in session:
        return redirect(url_for('partner_login'))
    partner_id = database._fetchone_scalar(
        "SELECT id_partner FROM partners WHERE LOWER(username)=LOWER(%s)",
        (session['partner'],),
        key='id_partner'
    )
    if not partner_id:
        return "Partener inexistent", 404
    return render_template('partners.html', partner_id=partner_id)


@app.route('/api/partners')
def api_partners():
    partners = database.get_partners()
    return (jsonify(partners), 200) if partners else (jsonify({'error': 'No partners'}), 404)


@app.route('/partners/<int:partner_id>/products')
def partner_products_page(partner_id):
    partner = database.get_partner(partner_id)
    if not partner:
        return "Partener inexistent", 404
    return render_template(
        'partner_products.html',
        partner_id=partner_id,
        partner_name=partner['name']
    )


@app.route('/api/partners/<int:partner_id>/products')
def api_partner_products(partner_id):
    prods = database.get_partner_products(partner_id)
    print("Products fetched:", prods)
    if prods is None:
        return jsonify({'error': 'Partner not found'}), 404
    return jsonify(prods)


@app.route('/api/partners/<int:partner_id>/products', methods=['POST'])
def api_set_partner_products(partner_id):
    partner = database.get_partner(partner_id)
    if not partner or session.get('partner', '').lower() != partner['username'].lower():
        return jsonify({'error': 'Not authorized'}), 403
    prices = (request.get_json() or {}).get('prices', [])
    res = database.upsert_partner_prices(partner_id, prices)
    return (jsonify(res), 200 if res.get('success') else 400)


@app.route('/api/employee/orders')
def api_employee_orders():
    if session.get('employee_dept') != 'sales':
        return jsonify({'error': 'Not authorized'}), 403
    eid = database.get_employee_id(session['employee'])
    data = database.get_orders_by_employee(eid)
    for o in data:
        o['qty'] = database.get_order_quantity(o['id_order'])
        o['date_fmt'] = o['data'].strftime('%Y-%m-%d %H:%M')
    return jsonify(data)


@app.route('/api/employee/update_order', methods=['POST'])
def api_employee_update_order():
    if session.get('employee_dept') != 'sales':
        return jsonify({'error': 'Not authorized'}), 403
    payload = request.get_json() or {}
    res = database.update_order_status(session['employee'], payload.get('order_id'), payload.get('status'))
    return (jsonify(res), 200 if res.get('success') else 400)


@app.route('/api/employee/productie/recipes', methods=['GET'])
def get_recipes():
    if session.get('employee_dept') != 'productie':
        return jsonify({'error': 'Not authorized'}), 403
    recipes = database.get_recipes()
    stock_rows = database.get_stock(final_only=False)
    stock_map = {row['id_product']: row for row in stock_rows}
    result = []
    for rec in recipes:
        ingredients = []
        for i in range(1, 6):
            mid = rec.get(f'id_material{i}')
            qty = rec.get(f'quantity_material{i}')
            if mid and qty:
                srow = stock_map.get(mid, {})
                ingredients.append({
                    'name': srow.get('name', f'ID {mid}'),
                    'quantity': qty,
                    'stock': srow.get('quantity', 0)
                })
        final = stock_map.get(rec['id_final'], {})
        result.append({
            'id_final': rec['id_final'],
            'final_name': final.get('name', f'ID {rec["id_final"]}'),
            'final_stock': final.get('quantity', 0),
            'ingredients': ingredients
        })
    return jsonify(result)


@app.route('/api/employee/productie/recipes', methods=['POST'])
def create_recipe():
    if session.get('employee_dept') != 'productie':
        return jsonify({'error': 'Not authorized'}), 403
    payload = request.get_json() or {}
    final_name = payload.get('final_name')
    ingredients = payload.get('ingredients', [])
    if not final_name or not isinstance(ingredients, list) or not ingredients:
        return jsonify({'error': 'Invalid input'}), 400
    res = database.add_recipe(final_name, ingredients)
    return (jsonify(res), 200 if res.get('success') else 400)


@app.route('/api/employee/productie/produce', methods=['POST'])
def produce_product():
    if session.get('employee_dept') != 'productie':
        return jsonify({'error': 'Not authorized'}), 403
    data = request.get_json() or {}
    recipe_id = data.get("recipe_id")
    quantity = data.get("quantity")
    res = database.produce_product(recipe_id, quantity)
    return (jsonify(res), 200 if res.get('success') else 400)


@app.route('/admin')
def admin_panel():
    return render_template('admin.html')


@app.route('/api/products', methods=['POST'])
def api_create_product():
    data = request.get_json(silent=True) or request.form
    name = data.get('name')
    price = data.get('price', type=float)
    description = data.get('description', '')
    quantity = data.get('quantity', type=int)
    ptype = data.get('type', 'final')
    if not name or price is None or quantity is None:
        return jsonify({'error': 'Nume, pret si cantitate sunt obligatorii'}), 400
    try:
        database.cursor.execute(
            "INSERT INTO stock (name,price,description,quantity,type) "
            "VALUES (%s,%s,%s,%s,%s)",
            (name, price, description, quantity, ptype)
        )
        database.connection.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        database.connection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/employees', methods=['POST'])
def api_create_employee():
    data = request.get_json(silent=True) or request.form
    print("Employee data received:", data)
    try:
        salary = float(data.get('salary', '').strip())
    except Exception:
        salary = None
    name = data.get('name')
    surname = data.get('surname')
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    department = data.get('department')
    phone_number = data.get('phone_number', '')
    address = data.get('address', '')
    if not all([name, surname, username, email, password,
                department, phone_number, address, salary]):
        return jsonify({'error': 'Toate câmpurile sunt obligatorii'}), 400
    try:
        database.cursor.execute(
            """
            INSERT INTO employees
              (name, surname, department, salary,
               email, phone_number, address,
               username, password)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (name, surname, department, salary,
             email, phone_number, address,
             username, password)
        )
        database.connection.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        traceback.print_exc()
        database.connection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/customers', methods=['POST'])
def api_create_customer():
    data = request.get_json(silent=True) or request.form
    name = data.get('name')
    surname = data.get('surname')
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    address = data.get('address', '')
    phone_number = data.get('phone_number', '')
    if not all([name, surname, username, email, password]):
        return jsonify({'error': 'Toate campurile sunt obligatorii'}), 400
    try:
        database.cursor.execute(
            "INSERT INTO customers (name, surname, username, email, password, address, phone_number) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (name, surname, username, email, password, address, phone_number)
        )
        database.connection.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        database.connection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/partners', methods=['POST'])
def api_create_partner():
    data = request.get_json(silent=True) or request.form
    name = data.get('name')
    username = data.get('username')
    password = data.get('password')
    address = data.get('address', '')
    phone_number = data.get('phone_number', '')
    email = data.get('email', '')
    if not name:
        return jsonify({'error': 'Nume partener obligatoriu'}), 400
    try:
        database.cursor.execute(
            "INSERT INTO partners (name, username, password, address, phone_number, email) VALUES (%s,%s,%s,%s,%s,%s)",
            (name, username, password, address, phone_number, email)
        )
        database.connection.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        database.connection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/recipes', methods=['POST'])
def api_create_recipe():
    data = request.get_json(silent=True) or request.form
    try:
        id_final = int(data.get('id_final'))
        final_qty = int(data.get('quantity'))
    except (TypeError, ValueError):
        return jsonify({'error': 'id_final și quantity trebuie numere întregi'}), 400
    materials = []
    for i in range(1, 6):
        mat = data.get(f'id_material{i}')
        qty = data.get(f'quantity_material{i}')
        if mat and qty:
            try:
                materials.append((int(mat), int(qty)))
            except ValueError:
                return jsonify({'error': f'Ingredient {i} invalid'}), 400
        else:
            materials.append((None, None))
    cols = ['id_final', 'quantity']
    vals = [id_final, final_qty]
    for idx, (mid, mqty) in enumerate(materials, start=1):
        cols.append(f'id_material{idx}')
        cols.append(f'quantity_material{idx}')
        vals.append(mid)
        vals.append(mqty)
    placeholders = ','.join(['%s'] * len(vals))
    col_sql = ','.join(cols)
    sql = f"INSERT INTO recipes ({col_sql}) VALUES ({placeholders})"
    try:
        database.cursor.execute(sql, tuple(vals))
        database.connection.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        database.connection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/partners/orders')
def partner_orders_page():
    if 'partner' not in session:
        return redirect(url_for('partner_login'))
    partner_id = database._fetchone_scalar(
        "SELECT id_partner FROM partners WHERE LOWER(username)=LOWER(%s)",
        (session['partner'],), key='id_partner')
    if not partner_id:
        return "Partener inexistent", 404
    return render_template('partner_orders.html', partner_id=partner_id)


@app.route('/api/partner/my_orders')
def api_partner_my_orders():
    if 'partner' not in session:
        return jsonify({'error': 'Not authorized'}), 403
    pid = database._fetchone_scalar(
        "SELECT id_partner FROM partners WHERE LOWER(username)=LOWER(%s)",
        (session['partner'],), key='id_partner')
    data = database.get_partner_orders_by_partner(pid)
    for r in data:
        r['date_fmt'] = r['data'].strftime('%Y-%m-%d %H:%M')
    return jsonify(data)


@app.route('/api/partner/update_order', methods=['POST'])
def api_partner_update_order():
    if 'partner' not in session:
        return jsonify({'error': 'Not authorized'}), 403
    payload = request.get_json() or {}
    pid = database._fetchone_scalar(
        "SELECT id_partner FROM partners WHERE LOWER(username)=LOWER(%s)",
        (session['partner'],), key='id_partner')
    res = database.update_partner_order_status(
        pid,
        payload.get('order_id'),
        payload.get('status'))
    return (jsonify(res), 200 if res.get('success') else 400)


@app.route('/staff')
def staff():
    rows = database.get_employees()
    achizitii = [e for e in rows if e['department'] == 'achizitii']
    vanzari = [e for e in rows if e['department'] == 'sales']
    productie = [e for e in rows if e['department'] == 'productie']
    return render_template('employees.html',
                           achizitii=achizitii,
                           vanzari=vanzari,
                           productie=productie)


if __name__ == '__main__':
    app.run(debug=True)
