from app import app, db
from app.db_classes import User


def max_challenge_rank_diff():
    return app.config['MAX_CHALLENGE_RANK_DIFF']


def place_at_bottom(user):
    """Assign a newly joining player the last position on the ladder."""
    bottom = db.session.query(db.func.max(User.rank)).scalar() or 0
    user.rank = bottom + 1


def challengeable_opponents(user):
    """Ranked players up to N places above the given (ranked) user."""
    if not user.rank:
        return []
    return (
        User.query.filter(
            User.id != user.id,
            User.rank > 0,
            User.rank < user.rank,
            User.rank >= user.rank - max_challenge_rank_diff(),
        )
        .order_by(User.rank)
        .all()
    )


def recordable_opponents(user):
    """Ranked players within N places of the given (ranked) user, in either direction."""
    if not user.rank:
        return []
    return (
        User.query.filter(
            User.id != user.id,
            User.rank > 0,
            User.rank >= user.rank - max_challenge_rank_diff(),
            User.rank <= user.rank + max_challenge_rank_diff(),
        )
        .order_by(User.rank)
        .all()
    )


def move_up(user):
    """Swap a ranked player with whoever is directly above them."""
    if not user.rank or user.rank <= 1:
        return
    above = User.query.filter_by(rank=user.rank - 1).first()
    if above:
        above.rank, user.rank = user.rank, above.rank


def move_down(user):
    """Swap a ranked player with whoever is directly below them."""
    if not user.rank:
        return
    below = User.query.filter_by(rank=user.rank + 1).first()
    if below:
        below.rank, user.rank = user.rank, below.rank


def apply_match_result(match):
    """Move the winner above the loser on the ladder if a lower-ranked
    player beat a higher-ranked opponent. Everyone previously between
    them drops down by one place. No-op if the winner was already
    ranked above the loser, or either player is unranked.
    """
    winner = match.winner
    if winner is None:
        return
    loser = match.player1 if winner.id == match.player2_id else match.player2

    if not winner.rank or not loser.rank or winner.rank <= loser.rank:
        return

    old_winner_rank = winner.rank
    old_loser_rank = loser.rank

    displaced = User.query.filter(
        User.rank >= old_loser_rank,
        User.rank < old_winner_rank,
    ).all()
    for u in displaced:
        u.rank += 1

    winner.rank = old_loser_rank
