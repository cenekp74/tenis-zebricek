import os
import uuid
import json
from app import app, db, bcrypt
from flask import render_template, url_for, request, redirect, abort, flash, send_from_directory
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.db_classes import User, Challenge, Match
from app.forms import LoginForm, EditProfileForm, ChallengeForm, RecordMatchForm
from app.email_utils import queue_email

TOKEN_MAX_AGE = 7 * 24 * 3600  # 7 days


def _make_match_token(match_id, opponent_id):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.dumps({'match_id': match_id, 'opponent_id': opponent_id})


def _load_match_token(token):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.loads(token, max_age=TOKEN_MAX_AGE)

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
        challenger: User = User.query.get(current_user.id)
        opponent: User = User.query.get(form.opponent.data)
        queue_email(
            subject=f"Výzva od hráče {challenger.name}",
            recipients=[opponent.email],
            template="challenge-email.html",
            reply_to=challenger.email,
            user=challenger,
            challenge=new_challenge,
        )
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
            if not sets or not all(isinstance(s, list) and len(s) == 2 for s in sets):
                raise ValueError('Neplatný formát setů.')
            def valid_regular_set(g1, g2):
                hi, lo = max(g1, g2), min(g1, g2)
                return (hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))

            last = sets[-1]
            last_is_tb = (int(last[0]) + int(last[1]) == 1 and max(int(last[0]), int(last[1])) == 1)

            if last_is_tb:
                regular = sets[:-1]
                if len(regular) != 2:
                    raise ValueError('Tiebreak je možný pouze jako rozhodující třetí set při stavu setů 1:1.')
                for s in regular:
                    g1, g2 = int(s[0]), int(s[1])
                    if not valid_regular_set(g1, g2):
                        raise ValueError(f'Neplatné skóre setu {g1}:{g2}.')
                p1r = sum(1 for s in regular if int(s[0]) > int(s[1]))
                if p1r != 1:
                    raise ValueError('Tiebreak je možný pouze jako rozhodující třetí set při stavu setů 1:1.')
            else:
                for s in sets:
                    g1, g2 = int(s[0]), int(s[1])
                    if not valid_regular_set(g1, g2):
                        raise ValueError(f'Neplatné skóre setu {g1}:{g2}.')
                if len(sets) < 2 or len(sets) > 3:
                    raise ValueError('Zápas musí mít 2 nebo 3 sety.')
                p1_sets = sum(1 for s in sets if int(s[0]) > int(s[1]))
                if p1_sets * 2 == len(sets):
                    raise ValueError('Zápas musí mít jasného vítěze.')
                p1r, p2r = 0, 0
                for s in sets[:-1]:
                    if int(s[0]) > int(s[1]): p1r += 1
                    else: p2r += 1
                    if p1r >= 2 or p2r >= 2:
                        raise ValueError('Zápas obsahuje nadbytečné sety.')
        except (ValueError, TypeError, KeyError) as exc:
            flash(str(exc) if str(exc) else 'Neplatný výsledek zápasu.', 'danger')
            return redirect(url_for('record_match'))

        opponent: User = User.query.get_or_404(opponent_id)

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

        token = _make_match_token(match.id, opponent_id)
        confirm_url = url_for('confirm_match', token=token, _external=True)
        queue_email(
            subject='Potvrďte výsledek zápasu',
            recipients=[opponent.email],
            template='match-confirmation-email.html',
            recorder=current_user,
            match=match,
            confirm_url=confirm_url,
        )

        flash('Výsledek byl uložen. Soupeř obdržel e-mail s žádostí o potvrzení.', 'success')
        return redirect(url_for('match_detail', match_id=match.id))

    return render_template('record_match.html', form=form)

@app.route('/matches')
def matches():
    all_matches = Match.query.order_by(Match.played_at.desc()).all()
    return render_template('matches.html', matches=all_matches)

@app.route('/matches/<int:match_id>')
def match_detail(match_id):
    match = Match.query.get_or_404(match_id)
    confirm_url = None
    if not match.verified and current_user.is_authenticated:
        opponent_id = match.player2_id if match.recorded_by_id == match.player1_id else match.player1_id
        if current_user.id == opponent_id:
            token = _make_match_token(match.id, opponent_id)
            confirm_url = url_for('confirm_match', token=token)
    return render_template('match_detail.html', match=match, confirm_url=confirm_url)


@app.route('/confirm-match/<token>')
def confirm_match(token):
    try:
        data = _load_match_token(token)
    except (SignatureExpired, BadSignature):
        flash('Odkaz pro potvrzení je neplatný nebo vypršel.', 'danger')
        return redirect(url_for('matches'))

    match = Match.query.get_or_404(data['match_id'])

    if match.verified:
        flash('Tento zápas již byl potvrzen.', 'info')
        return redirect(url_for('match_detail', match_id=match.id))

    expected_opponent_id = match.player2_id if match.recorded_by_id == match.player1_id else match.player1_id
    if data['opponent_id'] != expected_opponent_id:
        abort(403)

    match.verified = True
    db.session.commit()
    flash('Výsledek zápasu byl úspěšně potvrzen!', 'success')
    return redirect(url_for('match_detail', match_id=match.id))
