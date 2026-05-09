from flask import Flask , render_template

app = Flask(__name__)


@app.route('/')
def index():  # put application's code here
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/activities')
def activities():
    activities_list = [] #格式应为{title:... , date:... , content:...},{}
    if not activities_list:
        return render_template('no_activities.html')
    else:
        return render_template('activities.html', activities = activities_list)

#if __name__ == '__main__':
    app.run(host='0.0.0.0',port = 7891,debug=True)
