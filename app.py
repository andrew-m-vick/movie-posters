from flask import Flask, render_template, request
import requests
import os

app = Flask(__name__)

api_key = os.environ.get("OMDB_API_KEY")  # Pulled from Render env variable

def get_poster_url(movie_title):
    url = f"http://www.omdbapi.com/?t={movie_title}&apikey={api_key}"
    response = requests.get(url)
    data = response.json()

    if 'Poster' in data and data['Poster'] != 'N/A':
        poster_url = data['Poster']
        modified = poster_url[:poster_url.rfind("SX300")] + "0" + poster_url[poster_url.rfind("SX300"):]
        return modified, data.get('Title', movie_title)
    return None, None

@app.route("/", methods=["GET", "POST"])
def index():
    poster_url = None
    title = None
    error = None

    if request.method == "POST":
        movie_title = request.form.get("movie_title")
        poster_url, title = get_poster_url(movie_title)
        if not poster_url:
            error = f"No poster found for '{movie_title}'"

    return render_template("index.html", poster_url=poster_url, title=title, error=error)

if __name__ == "__main__":
    app.run(debug=True)