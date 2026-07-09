from flask import Flask, request, redirect, url_for, flash, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from flask_bcrypt import Bcrypt
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'campus_secret_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/Nupur/campus.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

db = SQLAlchemy(app)

class Student(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(100))
    college = db.Column(db.String(100))
    branch = db.Column(db.String(100))
    year = db.Column(db.Integer)
    bio = db.Column(db.Text)
    skills = db.Column(db.String(500))
    image_file = db.Column(db.String(20), default='default.jpg')
    is_online = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Integer, default=0)

class Connection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    to_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    status = db.Column(db.String(20), default='pending')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    is_read = db.Column(db.Integer, default=0)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm = request.form.get('confirm_password', '')
            
            # Validation
            if not username or not email or not password:
                flash('All fields are required!')
                return redirect(url_for('register'))
            
            if len(username) < 3:
                flash('Username must be at least 3 characters!')
                return redirect(url_for('register'))
            
            if len(password) < 4:
                flash('Password must be at least 4 characters!')
                return redirect(url_for('register'))
            
            if password != confirm:
                flash('Passwords do not match!')
                return redirect(url_for('register'))
            
            # Check username
            if Student.query.filter_by(username=username).first():
                flash('Username already taken!')
                return redirect(url_for('register'))
            
            # Check email
            if Student.query.filter_by(email=email).first():
                flash('Email already registered!')
                return redirect(url_for('register'))
            
            # Make first user admin
            is_admin = 1 if Student.query.count() == 0 else 0
            
            # Create user
            hashed = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = Student(
                username=username, 
                email=email, 
                password_hash=hashed, 
                is_admin=is_admin
            )
            db.session.add(new_user)
            db.session.commit()
            
            flash('Account created! Please login.')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}')
            return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        user = Student.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid email or password!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    search_query = request.args.get('q', '')
    if search_query:
        students = Student.query.filter(
            (Student.name.contains(search_query)) |
            (Student.username.contains(search_query)) |
            (Student.college.contains(search_query)) |
            (Student.branch.contains(search_query))
        ).filter(Student.id != current_user.id).all()
    else:
        students = Student.query.filter(Student.id != current_user.id).limit(20).all()
    
    my_connections = Connection.query.filter(
        ((Connection.from_id == current_user.id) | (Connection.to_id == current_user.id)) &
        (Connection.status == 'accepted')
    ).all()
    
    requests = Connection.query.filter(
        (Connection.to_id == current_user.id) &
        (Connection.status == 'pending')
    ).all()
    requesters = [Student.query.get(r.from_id) for r in requests]
    
    unread_count = Message.query.filter(
        (Message.receiver_id == current_user.id) &
        (Message.is_read == 0)
    ).count()
    
    score = 0
    if current_user.name: score += 20
    if current_user.college: score += 20
    if current_user.branch: score += 20
    if current_user.year: score += 20
    if current_user.bio: score += 20
    
    return render_template('dashboard.html', 
                      student=current_user, 
                      students=students,
                      connections=my_connections,
                      requests=requesters,
                      unread_count=unread_count,
                      score=score)

@app.route('/connect/<int:user_id>')
@login_required
def connect(user_id):
    if user_id == current_user.id:
        return redirect(url_for('dashboard'))
    
    existing = Connection.query.filter(
        ((Connection.from_id == current_user.id) & (Connection.to_id == user_id)) |
        ((Connection.from_id == user_id) & (Connection.to_id == current_user.id))
    ).first()
    
    if not existing:
        new_conn = Connection(from_id=current_user.id, to_id=user_id, status='pending')
        db.session.add(new_conn)
        db.session.commit()
        flash('Connection request sent!')
    else:
        flash('Already connected or request pending!')
    
    return redirect(url_for('profile', user_id=user_id))

@app.route('/accept/<int:user_id>')
@login_required
def accept(user_id):
    conn = Connection.query.filter(
        (Connection.from_id == user_id) &
        (Connection.to_id == current_user.id) &
        (Connection.status == 'pending')
    ).first()
    
    if conn:
        conn.status = 'accepted'
        db.session.commit()
        flash('Connection accepted!')
    
    return redirect(url_for('dashboard'))

@app.route('/reject/<int:user_id>')
@login_required
def reject(user_id):
    conn = Connection.query.filter(
        (Connection.from_id == user_id) &
        (Connection.to_id == current_user.id) &
        (Connection.status == 'pending')
    ).first()
    
    if conn:
        db.session.delete(conn)
        db.session.commit()
        flash('Request rejected.')
    
    return redirect(url_for('dashboard'))

@app.route('/profile', methods=['GET', 'POST'])
@app.route('/profile/<int:user_id>', methods=['GET', 'POST'])
@login_required
def profile(user_id=None):
    if user_id is None:
        user = current_user
    else:
        user = Student.query.get_or_404(user_id)
    is_own = (user == current_user)
    
    conn = Connection.query.filter(
        ((Connection.from_id == current_user.id) & (Connection.to_id == user.id)) |
        ((Connection.from_id == user.id) & (Connection.to_id == current_user.id))
    ).first()
    
    if conn:
        if conn.status == 'pending':
            if conn.from_id == current_user.id:
                status = 'Request Sent'
            else:
                status = 'Pending'
        else:
            status = 'Connected'
    else:
        status = 'Connect' if not is_own else None
    
    if request.method == 'POST' and is_own:
        user.name = request.form.get('name')
        user.college = request.form.get('college')
        user.branch = request.form.get('branch')
        user.year = request.form.get('year')
        user.bio = request.form.get('bio')
        user.skills = request.form.get('skills')
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[-1].lower()
                if ext in ['jpg', 'jpeg', 'png', 'gif']:
                    filename = f"{user.id}.{ext}"
                    os.makedirs('/home/Nupur/static/uploads', exist_ok=True)
                    file.save(os.path.join('/home/Nupur/static/uploads', filename))
                    user.image_file = filename
        
        db.session.commit()
        flash('Profile Updated!')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', profile_user=user, is_own=is_own, status=status)

@app.route('/messages')
@app.route('/messages/<int:selected_id>')
@login_required
def messages(selected_id=None):
    Message.query.filter(
        (Message.receiver_id == current_user.id) &
        (Message.is_read == 0)
    ).update({'is_read': 1})
    db.session.commit()
    
    connections = Connection.query.filter(
        ((Connection.from_id == current_user.id) | (Connection.to_id == current_user.id)) &
        (Connection.status == 'accepted')
    ).all()
    
    conversations = []
    selected_user = None
    chat_messages = []
    
    for c in connections:
        other_id = c.from_id if c.from_id != current_user.id else c.to_id
        other_user = Student.query.get(other_id)
        
        if other_user:
            last_msg = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == other_id)) |
                ((Message.sender_id == other_id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.timestamp.desc()).first()
            
            conversations.append({
                'user': other_user,
                'last_msg': last_msg
            })
            
            if selected_id and other_id == selected_id:
                selected_user = other_user
                chat_messages = Message.query.filter(
                    ((Message.sender_id == current_user.id) & (Message.receiver_id == selected_id)) |
                    ((Message.sender_id == selected_id) & (Message.receiver_id == current_user.id))
                ).order_by(Message.timestamp).all()
    
    return render_template('messages.html', 
                      conversations=conversations, 
                      selected_user=selected_user,
                      chat_messages=chat_messages)

@app.route('/send_message/<int:user_id>', methods=['POST'])
@login_required
def send_message(user_id):
    content = request.form.get('message')
    if content:
        ist_time = datetime.now() + timedelta(hours=5, minutes=30)
        new_msg = Message(
            sender_id=current_user.id, 
            receiver_id=user_id, 
            content=content,
            timestamp=ist_time
        )
        db.session.add(new_msg)
        db.session.commit()
    return redirect(url_for('messages', selected_id=user_id))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)