import os
from flask import Flask , render_template , url_for

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

@app.route('/gallery')
def gallery():
    # 定义照片文件夹的路径
    image_folder = os.path.join(app.static_folder, 'history_photos')
    # 获取该文件夹下所有文件的名称，并过滤出常见的图片格式
    image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
    # 生成每张图片的完整URL列表
    image_urls = [url_for('static', filename=f'history_photos/{img}') for img in image_files]
    # 将生成好的URL列表传递给 gallery.html 模板
    return render_template('gallery.html', image_urls=image_urls)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 7891))
    app.run(host='0.0.0.0', port=port, debug=False)
