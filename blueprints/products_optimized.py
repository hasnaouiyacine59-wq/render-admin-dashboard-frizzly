from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from firebase_admin import firestore
from extensions import firestore_extension
from utils import admin_required

products_bp = Blueprint('products', __name__)

@products_bp.route('/products')
@login_required
@admin_required
def products():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        products_ref = firestore_extension.db.collection('products').order_by('createdAt', direction=firestore.Query.DESCENDING)
        
        # Pagination
        products_query = products_ref.limit(per_page).offset((page - 1) * per_page)
        products_list = [{'id': doc.id, **doc.to_dict()} for doc in products_query.stream()]
        
        # Get total count
        try:
            total_count = firestore_extension.db.collection('products').count().get()[0][0].value
        except:
            total_count = sum(1 for _ in firestore_extension.db.collection('products').limit(1000).stream())
        
        total_pages = (total_count + per_page - 1) // per_page
        
        pagination = {
            'page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1,
            'next_num': page + 1
        }
        
        return render_template('products.html', products=products_list, pagination=pagination)
    except Exception as e:
        current_app.logger.error(f"Products error: {e}")
        pagination = {'page': 1, 'total_pages': 1, 'has_prev': False, 'has_next': False, 'prev_num': 1, 'next_num': 1}
        return render_template('products.html', products=[], pagination=pagination)

@products_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    if request.method == 'POST':
        try:
            product_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'price': float(request.form.get('price', 0)),
                'category': request.form.get('category'),
                'stock': int(request.form.get('stock', 0)),
                'imageUrl': request.form.get('imageUrl', ''),
                'isActive': request.form.get('isActive') == 'on',
                'createdAt': firestore.SERVER_TIMESTAMP
            }
            
            firestore_extension.db.collection('products').add(product_data)
            flash('Product added successfully', 'success')
            return redirect(url_for('products.products'))
        except Exception as e:
            current_app.logger.error(f"Add product error: {e}")
            flash('Failed to add product', 'error')
    
    # Fetch categories (limited)
    categories = []
    try:
        for cat_doc in firestore_extension.db.collection('categories').limit(100).stream():
            cat_data = cat_doc.to_dict()
            cat_data['id'] = cat_doc.id
            categories.append(cat_data)
    except Exception as e:
        current_app.logger.error(f"Load categories error: {e}")
    
    return render_template('add_product.html', categories=categories)

@products_bp.route('/products/<product_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    if request.method == 'POST':
        try:
            product_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'price': float(request.form.get('price', 0)),
                'category': request.form.get('category'),
                'stock': int(request.form.get('stock', 0)),
                'imageUrl': request.form.get('imageUrl', ''),
                'isActive': request.form.get('isActive') == 'on',
                'updatedAt': firestore.SERVER_TIMESTAMP
            }
            
            firestore_extension.db.collection('products').document(product_id).update(product_data)
            flash('Product updated successfully', 'success')
            return redirect(url_for('products.products'))
        except Exception as e:
            current_app.logger.error(f"Edit product error: {e}")
            flash('Failed to update product', 'error')
    
    try:
        doc = firestore_extension.db.collection('products').document(product_id).get()
        if not doc.exists:
            flash('Product not found', 'error')
            return redirect(url_for('products.products'))
        
        product = doc.to_dict()
        product['id'] = doc.id
        
        # Fetch categories (limited)
        categories = []
        for cat_doc in firestore_extension.db.collection('categories').limit(100).stream():
            cat_data = cat_doc.to_dict()
            cat_data['id'] = cat_doc.id
            categories.append(cat_data)
        
        return render_template('edit_product.html', product=product, categories=categories)
    except Exception as e:
        current_app.logger.error(f"Load product error: {e}")
        flash('Error loading product', 'error')
        return redirect(url_for('products.products'))

@products_bp.route('/products/<product_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    try:
        firestore_extension.db.collection('products').document(product_id).delete()
        flash('Product deleted successfully', 'success')
    except Exception as e:
        current_app.logger.error(f"Delete product error: {e}")
        flash('Failed to delete product', 'error')
    
    return redirect(url_for('products.products'))

@products_bp.route('/products/<product_id>/update-stock', methods=['POST'])
@login_required
@admin_required
def update_stock(product_id):
    try:
        new_stock = int(request.form.get('stock', 0))
        firestore_extension.db.collection('products').document(product_id).update({
            'stock': new_stock,
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        flash('Stock updated successfully', 'success')
    except Exception as e:
        current_app.logger.error(f"Update stock error: {e}")
        flash('Failed to update stock', 'error')
    return redirect(url_for('products.products'))
