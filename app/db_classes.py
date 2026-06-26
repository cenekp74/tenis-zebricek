from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timezone

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String, unique=False, nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password = db.Column(db.String(60), nullable=False)
    admin = db.Column(db.Integer, nullable=False, default=0)
    pp_filename = db.Column(db.String(64), nullable=False, default="default_pp.png")
    rank = db.Column(db.Integer, unique=False, nullable=False, default=0) # 0 means unranked

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    challenger_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    opponent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    challenger = db.relationship('User', foreign_keys=[challenger_id], backref='challenges_sent')
    opponent = db.relationship('User', foreign_keys=[opponent_id], backref='challenges_received')

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    player1_rank = db.Column(db.Integer, nullable=False)
    player2_rank = db.Column(db.Integer, nullable=False)
    sets = db.Column(db.JSON, nullable=False)  # [[p1_games, p2_games], ...]
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'), nullable=True)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    played_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    recorded_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    player1 = db.relationship('User', foreign_keys=[player1_id], backref='matches_as_player1')
    player2 = db.relationship('User', foreign_keys=[player2_id], backref='matches_as_player2')
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_id])
    challenge = db.relationship('Challenge', foreign_keys=[challenge_id])
