from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from app.db_classes import User

class EditProfileForm(FlaskForm):
    picture = FileField('Profilová fotografie', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Povolené formáty: jpg, jpeg, png, webp.')
    ])
    submit = SubmitField('Uložit')

class ChallengeForm(FlaskForm):
    opponent = SelectField('Protihráč', coerce=int, validators=[DataRequired()])
    message = TextAreaField('Zpráva (nepovinná)')
    submit = SubmitField('Vyzvat')

class RecordMatchForm(FlaskForm):
    opponent = SelectField('Protihráč', coerce=int, validators=[DataRequired()])
    sets_data = HiddenField('Sety')
    submit = SubmitField('Uložit výsledek')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Heslo', validators=[DataRequired()])
    remember = BooleanField('Pamatuj si mě')
    submit = SubmitField('Přihlásit')

class AddPlayerForm(FlaskForm):
    name = StringField('Jméno', validators=[DataRequired()])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Odeslat pozvánku')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Hráč s tímto e-mailem už je zaregistrovaný.')

class CompleteInviteForm(FlaskForm):
    username = StringField('Uživatelské jméno', validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('Heslo', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Heslo znovu', validators=[DataRequired(), EqualTo('password', message='Hesla se neshodují.')])
    picture = FileField('Profilová fotografie (nepovinná)', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Povolené formáty: jpg, jpeg, png, webp.')
    ])
    submit = SubmitField('Dokončit registraci')

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('Toto uživatelské jméno je již obsazené.')

class AdminActionForm(FlaskForm):
    """CSRF-only form backing the up/down/place buttons on the admin ranking page."""
    pass

class RequestPasswordResetForm(FlaskForm):
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Odeslat odkaz pro obnovu hesla')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Nové heslo', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Nové heslo znovu', validators=[DataRequired(), EqualTo('password', message='Hesla se neshodují.')])
    submit = SubmitField('Změnit heslo')
