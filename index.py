import os
from flask import Flask, render_template, send_file, request, make_response
import badcinema as source

app = Flask(__name__)


@app.route('/')
def hello_world():
    SW = source.SerialWorker()
    info = SW.get_serial_info()
    return render_template("index.html",
                           title='Home',
                           info=info)


@app.route('/cache/<string:poster_id>')
def cache(poster_id):
    folder_name = poster_id[:2]
    return send_file(os.path.join('cache', folder_name, poster_id))


@app.route('/download')
def download():
    SW = source.SerialWorker()
    SW.download_serial(request.args.get('id'))
    return make_response("", 200)


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
