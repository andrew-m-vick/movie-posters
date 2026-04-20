import os
from flask import Flask, send_file, send_from_directory

app = Flask(__name__)

@app.route('/')
def index():
    return send_file('index.html')

# Browsers look for /favicon.ico at the root by default
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

# iOS looks for apple-touch-icon at the root level
@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    return send_from_directory('static', 'apple-touch-icon.png')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
