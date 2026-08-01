import os
import uuid
import json
from app import app, db, bcrypt
from flask import render_template, url_for, request, redirect, abort, flash, send_from_directory
from markupsafe import Markup
from sqlalchemy import or_
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.db_classes import User, Challenge, Match
from app.forms import LoginForm, EditProfileForm, ChallengeForm, RecordMatchForm, AddPlayerForm, CompleteInviteForm, AdminActionForm, RequestPasswordResetForm, ResetPasswordForm
from app.email_utils import queue_email
from app.ladder import apply_match_result, challengeable_opponents, recordable_opponents, max_challenge_rank_diff, place_at_bottom, move_up, move_down, remove_from_ladder
from app.utils import admin_required

TOKEN_MAX_AGE = 7 * 24 * 3600  # 7 days
INVITE_TOKEN_MAX_AGE = 7 * 24 * 3600  # 7 days
RESET_TOKEN_MAX_AGE = 3600  # 1 hour
DEFAULT_PP_FILENAME = 'default_pp.png'


def _make_match_token(match_id, opponent_id):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.dumps({'match_id': match_id, 'opponent_id': opponent_id})


def _load_match_token(token):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.loads(token, max_age=TOKEN_MAX_AGE)


def _make_invite_token(user_id):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.dumps({'user_id': user_id}, salt='invite')


def _load_invite_token(token):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.loads(token, max_age=INVITE_TOKEN_MAX_AGE, salt='invite')


def _make_reset_token(user):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.dumps({'user_id': user.id, 'pw_hash': user.password}, salt='reset-password')


def _load_reset_token(token):
    s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return s.loads(token, max_age=RESET_TOKEN_MAX_AGE, salt='reset-password')

MAX_PP_SIZE = 2 * 1024 * 1024  # 2 MB


def _save_profile_picture(picture_file, old_filename=None):
    """Validate and store an uploaded profile picture, returning its new filename."""
    picture_file.seek(0, 2)
    size = picture_file.tell()
    picture_file.seek(0)
    if size > MAX_PP_SIZE:
        raise ValueError(f'Soubor je příliš velký (max {int(MAX_PP_SIZE/(1024**2))} MB).')

    ext = os.path.splitext(secure_filename(picture_file.filename))[1].lower()
    filename = uuid.uuid4().hex + ext
    pp_dir = os.path.join(app.instance_path, 'pp')
    os.makedirs(pp_dir, exist_ok=True)

    if old_filename and old_filename != DEFAULT_PP_FILENAME:
        old_path = os.path.join(pp_dir, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    picture_file.save(os.path.join(pp_dir, filename))
    return filename

@app.route('/')
@app.route('/index')
def index():
    return redirect(url_for('zebricek'))

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
            try:
                current_user.pp_filename = _save_profile_picture(pp, current_user.pp_filename)
            except ValueError as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('profile'))
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
    can_challenge = (
        current_user.is_authenticated
        and current_user.id != user.id
        and current_user.rank
        and user.rank
        and user.rank < current_user.rank
        and current_user.rank - user.rank <= max_challenge_rank_diff()
    )
    matches = Match.query.filter(
        or_(Match.player1_id == user.id, Match.player2_id == user.id)
    ).order_by(Match.played_at.desc()).all()
    return render_template('public_profile.html', user=user, can_challenge=can_challenge, matches=matches)

@app.route('/challenge', methods=['GET', 'POST'])
@login_required
def challenge():
    if not current_user.rank:
        flash('Nejste zatím zařazen/a v žebříčku, tudíž nemůžete nikoho vyzvat.', 'danger')
        return redirect(url_for('zebricek'))

    form = ChallengeForm()
    opponents = challengeable_opponents(current_user)
    form.opponent.choices = [
        (u.id, f"{u.name} (#{u.rank})")
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
    return render_template('challenge.html', form=form, max_challenge_rank_diff=max_challenge_rank_diff())

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
        login_value = form.username.data
        user = User.query.filter(
            or_(User.username == login_value, User.email == login_value)
        ).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect('/')
        flash(Markup(
            'Nesprávné uživatelské jméno nebo heslo. '
            f'<a href="{url_for("forgot_password")}">Zapomněli jste heslo?</a>'
        ), 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = RequestPasswordResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.is_registered:
            token = _make_reset_token(user)
            reset_url = url_for('reset_password', token=token, _external=True)
            queue_email(
                subject='Obnova hesla – žebříček TJ Astra tenis',
                recipients=[user.email],
                template='reset-password-email.html',
                name=user.name,
                reset_url=reset_url,
            )
        flash('Pokud e-mail existuje v systému, byl na něj odeslán odkaz pro obnovu hesla.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html', form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        data = _load_reset_token(token)
    except (SignatureExpired, BadSignature):
        flash('Odkaz pro obnovu hesla je neplatný nebo vypršel.', 'danger')
        return redirect(url_for('forgot_password'))

    user = User.query.get_or_404(data['user_id'])
    if user.password != data['pw_hash']:
        flash('Odkaz pro obnovu hesla je neplatný nebo už byl použit.', 'danger')
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        db.session.commit()
        flash('Heslo bylo úspěšně změněno. Přihlaste se.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form, name=user.name)

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/ranking')
@admin_required
def admin_ranking():
    ranked = User.query.filter(User.rank > 0).order_by(User.rank).all()
    unranked = User.query.filter(User.rank == 0).order_by(User.id).all()
    return render_template('admin_ranking.html', ranked=ranked, unranked=unranked, form=AdminActionForm())

@app.route('/admin/ranking/<int:user_id>/up', methods=['POST'])
@admin_required
def admin_ranking_up(user_id):
    if AdminActionForm().validate_on_submit():
        move_up(User.query.get_or_404(user_id))
        db.session.commit()
    return redirect(url_for('admin_ranking'))

@app.route('/admin/ranking/<int:user_id>/down', methods=['POST'])
@admin_required
def admin_ranking_down(user_id):
    if AdminActionForm().validate_on_submit():
        move_down(User.query.get_or_404(user_id))
        db.session.commit()
    return redirect(url_for('admin_ranking'))

@app.route('/admin/ranking/<int:user_id>/place', methods=['POST'])
@admin_required
def admin_ranking_place(user_id):
    if AdminActionForm().validate_on_submit():
        user = User.query.get_or_404(user_id)
        if not user.rank:
            place_at_bottom(user)
            db.session.commit()
    return redirect(url_for('admin_ranking'))

@app.route('/admin/players/<int:user_id>/delete', methods=['GET', 'POST'])
@admin_required
def delete_player(user_id):
    user = User.query.get_or_404(user_id)
    match_count = Match.query.filter(
        (Match.player1_id == user.id) | (Match.player2_id == user.id) | (Match.recorded_by_id == user.id)
    ).count()
    challenge_count = Challenge.query.filter(
        (Challenge.challenger_id == user.id) | (Challenge.opponent_id == user.id)
    ).count()
    can_delete = match_count == 0 and challenge_count == 0

    form = AdminActionForm()
    if can_delete and form.validate_on_submit():
        remove_from_ladder(user)
        if user.pp_filename and user.pp_filename != DEFAULT_PP_FILENAME:
            pp_path = os.path.join(app.instance_path, 'pp', user.pp_filename)
            if os.path.exists(pp_path):
                os.remove(pp_path)
        db.session.delete(user)
        db.session.commit()
        flash(f'Hráč {user.name} byl odstraněn.', 'success')
        return redirect(url_for('admin_ranking'))

    return render_template(
        'admin_delete_player.html',
        user=user,
        form=form,
        can_delete=can_delete,
        match_count=match_count,
        challenge_count=challenge_count,
    )

@app.route('/admin/add-player', methods=['GET', 'POST'])
@admin_required
def add_player():
    form = AddPlayerForm()
    if form.validate_on_submit():
        user = User(name=form.name.data, email=form.email.data)
        db.session.add(user)
        db.session.commit()

        token = _make_invite_token(user.id)
        accept_url = url_for('accept_invite', token=token, _external=True)
        queue_email(
            subject='Pozvánka do žebříčku TJ Astra tenis',
            recipients=[user.email],
            template='invite-email.html',
            name=user.name,
            accept_url=accept_url,
        )
        flash(f'Hráč {user.name} byl přidán do žebříčku a pozvánka byla odeslána na e-mail {user.email}.', 'success')
        return redirect(url_for('zebricek'))
    return render_template('admin_add_player.html', form=form)

@app.route('/invite/<token>', methods=['GET', 'POST'])
def accept_invite(token):
    try:
        data = _load_invite_token(token)
    except (SignatureExpired, BadSignature):
        flash('Odkaz pro dokončení registrace je neplatný nebo vypršel.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get_or_404(data['user_id'])

    if user.is_registered:
        flash('Tento účet už byl dokončen. Přihlaste se.', 'info')
        return redirect(url_for('login'))

    form = CompleteInviteForm()
    if form.validate_on_submit():
        user.username = form.username.data
        user.password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')

        pp = form.picture.data
        if pp:
            try:
                user.pp_filename = _save_profile_picture(pp)
            except ValueError as exc:
                flash(str(exc), 'danger')
                return render_template('accept_invite.html', form=form, name=user.name)

        db.session.commit()
        login_user(user)
        flash('Účet byl úspěšně vytvořen. Vítejte!', 'success')
        return redirect(url_for('index'))
    return render_template('accept_invite.html', form=form, name=user.name)

@app.route('/record-match', methods=['GET', 'POST'])
@login_required
def record_match():
    if not current_user.rank:
        flash('Nejste zatím zařazen/a v žebříčku, tudíž nemůžete zaznamenat výsledek.', 'danger')
        return redirect(url_for('zebricek'))

    form = RecordMatchForm()
    opponents = recordable_opponents(current_user)
    form.opponent.choices = [
        (u.id, f"{u.name} (#{u.rank})")
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

    return render_template('record_match.html', form=form, max_challenge_rank_diff=max_challenge_rank_diff())

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
    apply_match_result(match)
    db.session.commit()
    flash('Výsledek zápasu byl úspěšně potvrzen!', 'success')
    return redirect(url_for('match_detail', match_id=match.id))
