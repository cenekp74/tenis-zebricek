from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, TextAreaField, HiddenField
from wtforms.validators import DataRequired

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
