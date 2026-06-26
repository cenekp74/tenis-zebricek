import os
import uuid
import json
from app import app, db, bcrypt
from flask import render_template, url_for, request, redirect, abort, flash, send_from_directory
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.utils import secure_filename
from app.db_classes import User, Challenge, Match
from app.forms import LoginForm, EditProfileForm, ChallengeForm, RecordMatchForm

MAX_PP_SIZE = 2 * 1024 * 1024  # 2 MB

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/zebricek')
def zebricek():
    users = sorted(User.query.all(), key=lambda u: (u.rank == 0, u.rank))
    return render_template('zebricek.html', players=users)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        pp = form.picture.data
        if pp:
            pp.seek(0, 2)
            size = pp.tell()
            pp.seek(0)
            if size > MAX_PP_SIZE:
                flash(f'Soubor je příliš velký (max {int(MAX_PP_SIZE/(1024**2))} MB).', 'danger')
                return redirect(url_for('profile'))

            ext = os.path.splitext(secure_filename(pp.filename))[1].lower()
            filename = uuid.uuid4().hex + ext
            pp_dir = os.path.join(app.instance_path, 'pp')
            os.makedirs(pp_dir, exist_ok=True)

            if current_user.pp_filename:
                old_path = os.path.join(pp_dir, current_user.pp_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)

            pp.save(os.path.join(pp_dir, filename))
            current_user.pp_filename = filename
            db.session.commit()
            flash('Profilová fotografie byla aktualizována.', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html', form=form)

@app.route('/uploads/pp/<filename>')
@login_required
def profile_picture(filename):
    return send_from_directory(os.path.join(app.instance_path, 'pp'), filename)

@app.route('/uploads/pp/public/<filename>')
def public_profile_picture(filename):
    return send_from_directory(os.path.join(app.instance_path, 'pp'), filename)

@app.route('/u/<username>')
def public_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template('public_profile.html', user=user)

@app.route('/challenge', methods=['GET', 'POST'])
@login_required
def challenge():
    form = ChallengeForm()
    opponents = User.query.filter(User.id != current_user.id).order_by(User.rank).all()
    form.opponent.choices = [
        (u.id, f"{u.name} (#{u.rank if u.rank > 0 else '—'})")
        for u in opponents
    ]
    if request.method == 'GET':
        preselect = request.args.get('opponent', type=int)
        if preselect:
            form.opponent.data = preselect
    if form.validate_on_submit():
        new_challenge = Challenge(
            challenger_id=current_user.id,
            opponent_id=form.opponent.data,
            message=form.message.data or None
        )
        db.session.add(new_challenge)
        db.session.commit()
        flash('Výzva byla odeslána!', 'success')
        return redirect('/')
    return render_template('challenge.html', form=form)

@app.route('/my-challenges')
@login_required
def my_challenges():
    received = Challenge.query.filter_by(opponent_id=current_user.id).order_by(Challenge.created_at.desc()).all()
    sent = Challenge.query.filter_by(challenger_id=current_user.id).order_by(Challenge.created_at.desc()).all()
    return render_template('my_challenges.html', received=received, sent=sent)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect('/')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/record-match', methods=['GET', 'POST'])
@login_required
def record_match():
    form = RecordMatchForm()
    opponents = User.query.filter(User.id != current_user.id).order_by(User.rank).all()
    form.opponent.choices = [
        (u.id, f"{u.name} (#{u.rank if u.rank > 0 else '—'})")
        for u in opponents
    ]

    if request.method == 'GET':
        preselect = request.args.get('opponent', type=int)
        if preselect:
            form.opponent.data = preselect

    if form.validate_on_submit():
        opponent_id = form.opponent.data
        try:
            sets = json.loads(form.sets_data.data or '[]')
            print(form.sets_data.data)
            if not sets or not all(isinstance(s, list) and len(s) == 2 for s in sets):
                raise ValueError
        except (ValueError, TypeError):
            flash('Zadejte skóre alespoň jednoho setu.', 'danger')
            return redirect(url_for('record_match'))

        opponent = User.query.get_or_404(opponent_id)

        match = Match(
            player1_id=current_user.id,
            player2_id=opponent_id,
            player1_rank=current_user.rank,
            player2_rank=opponent.rank,
            sets=sets,
            recorded_by_id=current_user.id,
        )
        db.session.add(match)
        db.session.commit()
        flash('Výsledek byl uložen.', 'success')
        return redirect(url_for('match_detail', match_id=match.id))

    return render_template('record_match.html', form=form)

@app.route('/matches')
def matches():
    all_matches = Match.query.order_by(Match.played_at.desc()).all()
    return render_template('matches.html', matches=all_matches)

@app.route('/matches/<int:match_id>')
def match_detail(match_id):
    match = Match.query.get_or_404(match_id)
    return render_template('match_detail.html', match=match)
