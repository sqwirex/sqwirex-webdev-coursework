import os
import uuid
from pathlib import Path

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from werkzeug.utils import secure_filename

from . import db
from .decorators import roles_required
from .models import Category, Material, Role, StoredFile, User


def allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_uploaded_files(files, material, app_config):
    upload_folder = app_config['UPLOAD_FOLDER']
    allowed_extensions = app_config['ALLOWED_EXTENSIONS']

    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename, allowed_extensions):
            flash(f'Файл {file.filename} имеет недопустимое расширение.', 'danger')
            continue

        original_name = secure_filename(file.filename)
        extension = original_name.rsplit('.', 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{extension}"
        file_path = os.path.join(upload_folder, stored_name)
        file.save(file_path)

        stored_file = StoredFile(
            original_name=original_name,
            stored_name=stored_name,
            file_path=file_path,
            material=material,
        )
        db.session.add(stored_file)


def can_manage_material(material: Material) -> bool:
    return current_user.has_role('admin') or material.author_id == current_user.id


def register_routes(app):
    @app.route('/')
    def index():
        materials = Material.query.order_by(Material.created_at.desc()).limit(5).all()
        return render_template('index.html', materials=materials)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password):
                login_user(user)
                flash('Вход выполнен успешно.', 'success')
                return redirect(url_for('index'))

            flash('Неверный логин или пароль.', 'danger')
        return render_template('auth/login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Вы вышли из системы.', 'info')
        return redirect(url_for('login'))

    @app.route('/users')
    @login_required
    @roles_required('admin')
    def users_list():
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('users/list.html', users=users)

    @app.route('/users/create', methods=['GET', 'POST'])
    @login_required
    @roles_required('admin')
    def users_create():
        roles = Role.query.filter(Role.name.in_(['admin', 'teacher', 'student'])).order_by(Role.name).all()
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            full_name = request.form.get('full_name', '').strip()
            password = request.form.get('password', '')
            role_id = request.form.get('role_id', type=int)

            if not username or not full_name or not password or not role_id:
                flash('Заполните все обязательные поля.', 'danger')
                return render_template('users/form.html', roles=roles, user_obj=None)

            if User.query.filter_by(username=username).first():
                flash('Пользователь с таким логином уже существует.', 'danger')
                return render_template('users/form.html', roles=roles, user_obj=None)

            role = Role.query.get_or_404(role_id)
            user = User(username=username, full_name=full_name, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Пользователь создан.', 'success')
            return redirect(url_for('users_list'))

        return render_template('users/form.html', roles=roles, user_obj=None)

    @app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
    @login_required
    @roles_required('admin')
    def users_edit(user_id):
        user = User.query.get_or_404(user_id)
        roles = Role.query.filter(Role.name.in_(['admin', 'teacher', 'student'])).order_by(Role.name).all()

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            full_name = request.form.get('full_name', '').strip()
            password = request.form.get('password', '')
            role_id = request.form.get('role_id', type=int)

            existing_user = User.query.filter(User.username == username, User.id != user.id).first()
            if existing_user:
                flash('Пользователь с таким логином уже существует.', 'danger')
                return render_template('users/form.html', roles=roles, user_obj=user)

            user.username = username
            user.full_name = full_name
            user.role_id = role_id
            if password:
                user.set_password(password)

            db.session.commit()
            flash('Пользователь обновлён.', 'success')
            return redirect(url_for('users_list'))

        return render_template('users/form.html', roles=roles, user_obj=user)

    @app.route('/users/<int:user_id>/delete', methods=['POST'])
    @login_required
    @roles_required('admin')
    def users_delete(user_id):
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            flash('Нельзя удалить текущего администратора.', 'danger')
            return redirect(url_for('users_list'))

        db.session.delete(user)
        db.session.commit()
        flash('Пользователь удалён.', 'info')
        return redirect(url_for('users_list'))

    @app.route('/categories')
    @login_required
    @roles_required('admin', 'teacher')
    def categories_list():
        categories = Category.query.order_by(Category.name).all()
        return render_template('categories/list.html', categories=categories)

    @app.route('/categories/create', methods=['GET', 'POST'])
    @login_required
    @roles_required('admin')
    def categories_create():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            if not name:
                flash('Введите название категории.', 'danger')
                return render_template('categories/form.html', category=None)
            if Category.query.filter_by(name=name).first():
                flash('Такая категория уже существует.', 'danger')
                return render_template('categories/form.html', category=None)
            category = Category(name=name, description=description)
            db.session.add(category)
            db.session.commit()
            flash('Категория создана.', 'success')
            return redirect(url_for('categories_list'))
        return render_template('categories/form.html', category=None)

    @app.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
    @login_required
    @roles_required('admin')
    def categories_edit(category_id):
        category = Category.query.get_or_404(category_id)
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            existing = Category.query.filter(Category.name == name, Category.id != category.id).first()
            if existing:
                flash('Такая категория уже существует.', 'danger')
                return render_template('categories/form.html', category=category)
            category.name = name
            category.description = description
            db.session.commit()
            flash('Категория обновлена.', 'success')
            return redirect(url_for('categories_list'))
        return render_template('categories/form.html', category=category)

    @app.route('/categories/<int:category_id>/delete', methods=['POST'])
    @login_required
    @roles_required('admin')
    def categories_delete(category_id):
        category = Category.query.get_or_404(category_id)
        if category.materials:
            flash('Нельзя удалить категорию, в которой есть материалы.', 'danger')
            return redirect(url_for('categories_list'))
        db.session.delete(category)
        db.session.commit()
        flash('Категория удалена.', 'info')
        return redirect(url_for('categories_list'))

    @app.route('/materials')
    @login_required
    def materials_list():
        query = Material.query.order_by(Material.created_at.desc())
        category_filter = request.args.get('category_id', type=int)
        if category_filter:
            query = query.filter_by(category_id=category_filter)

        if current_user.has_role('student'):
            materials = query.all()
        elif current_user.has_role('teacher'):
            materials = query.all()
        else:
            materials = query.all()

        categories = Category.query.order_by(Category.name).all()
        return render_template('materials/list.html', materials=materials, categories=categories, category_filter=category_filter)

    @app.route('/materials/<int:material_id>')
    @login_required
    def materials_detail(material_id):
        material = Material.query.get_or_404(material_id)
        return render_template('materials/detail.html', material=material)

    @app.route('/materials/create', methods=['GET', 'POST'])
    @login_required
    @roles_required('admin', 'teacher')
    def materials_create():
        categories = Category.query.order_by(Category.name).all()
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            category_id = request.form.get('category_id', type=int)
            if not title or not category_id:
                flash('Заполните обязательные поля.', 'danger')
                return render_template('materials/form.html', material=None, categories=categories)

            material = Material(
                title=title,
                description=description,
                category_id=category_id,
                author_id=current_user.id,
            )
            db.session.add(material)
            db.session.flush()

            save_uploaded_files(request.files.getlist('files'), material, app.config)
            db.session.commit()
            flash('Материал создан.', 'success')
            return redirect(url_for('materials_detail', material_id=material.id))

        return render_template('materials/form.html', material=None, categories=categories)

    @app.route('/materials/<int:material_id>/edit', methods=['GET', 'POST'])
    @login_required
    @roles_required('admin', 'teacher')
    def materials_edit(material_id):
        material = Material.query.get_or_404(material_id)
        if not can_manage_material(material):
            abort(403)

        categories = Category.query.order_by(Category.name).all()
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            category_id = request.form.get('category_id', type=int)
            if not title or not category_id:
                flash('Заполните обязательные поля.', 'danger')
                return render_template('materials/form.html', material=material, categories=categories)

            material.title = title
            material.description = description
            material.category_id = category_id
            save_uploaded_files(request.files.getlist('files'), material, app.config)
            db.session.commit()
            flash('Материал обновлён.', 'success')
            return redirect(url_for('materials_detail', material_id=material.id))

        return render_template('materials/form.html', material=material, categories=categories)

    @app.route('/materials/<int:material_id>/delete', methods=['POST'])
    @login_required
    @roles_required('admin', 'teacher')
    def materials_delete(material_id):
        material = Material.query.get_or_404(material_id)
        if not can_manage_material(material):
            abort(403)

        for file in material.files:
            if os.path.exists(file.file_path):
                os.remove(file.file_path)
        db.session.delete(material)
        db.session.commit()
        flash('Материал удалён.', 'info')
        return redirect(url_for('materials_list'))

    @app.route('/files/<int:file_id>/download')
    @login_required
    def files_download(file_id):
        file = StoredFile.query.get_or_404(file_id)
        directory = os.path.dirname(file.file_path)
        return send_from_directory(directory, file.stored_name, as_attachment=True, download_name=file.original_name)

    @app.route('/files/<int:file_id>/delete', methods=['POST'])
    @login_required
    @roles_required('admin', 'teacher')
    def files_delete(file_id):
        file = StoredFile.query.get_or_404(file_id)
        if not can_manage_material(file.material):
            abort(403)

        if os.path.exists(file.file_path):
            os.remove(file.file_path)
        material_id = file.material_id
        next_view = request.form.get('next', 'detail')
        db.session.delete(file)
        db.session.commit()
        flash('Файл удалён.', 'info')
        if next_view == 'edit':
            return redirect(url_for('materials_edit', material_id=material_id))
        return redirect(url_for('materials_detail', material_id=material_id))

    @app.route('/stats')
    @login_required
    @roles_required('admin')
    def stats_index():
        materials_by_category = (
            db.session.query(Category.name, func.count(Material.id))
            .outerjoin(Material, Material.category_id == Category.id)
            .group_by(Category.id)
            .order_by(Category.name)
            .all()
        )
        materials_by_author_rows = (
            db.session.query(User, func.count(Material.id))
            .outerjoin(Material, Material.author_id == User.id)
            .filter(User.role.has(name='teacher') | User.role.has(name='admin'))
            .group_by(User.id)
            .order_by(User.full_name, User.username)
            .all()
        )
        materials_by_author = [(user.display_name, count) for user, count in materials_by_author_rows]
        role_counts = (
            db.session.query(Role.name, func.count(User.id))
            .outerjoin(User, User.role_id == Role.id)
            .group_by(Role.id)
            .order_by(Role.name)
            .all()
        )
        total_files = StoredFile.query.count()
        total_materials = Material.query.count()
        return render_template(
            'stats/index.html',
            materials_by_category=materials_by_category,
            materials_by_author=materials_by_author,
            role_counts=role_counts,
            total_files=total_files,
            total_materials=total_materials,
        )

    @app.errorhandler(401)
    def unauthorized(_error):
        return render_template('errors.html', code=401, message='Требуется авторизация.'), 401

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template('errors.html', code=403, message='Доступ запрещён.'), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template('errors.html', code=404, message='Страница не найдена.'), 404