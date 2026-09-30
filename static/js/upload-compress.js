(function () {
    const MAX_DIMENSION = 800;
    const JPEG_QUALITY = 0.85;
    const MAX_FILE_SIZE = 20 * 1024 * 1024;

    function compressFile(file) {
        return new Promise(function (resolve, reject) {
            if (!file.type || !file.type.startsWith('image/')) {
                resolve(file);
                return;
            }
            if (file.type === 'image/gif') {
                resolve(file);
                return;
            }
            if (file.size > MAX_FILE_SIZE) {
                reject(new Error('图片太大（超过 20MB）'));
                return;
            }

            const reader = new FileReader();
            reader.onload = function (e) {
                const img = new Image();
                img.onload = function () {
                    let w = img.width;
                    let h = img.height;

                    if (w > MAX_DIMENSION || h > MAX_DIMENSION) {
                        if (w > h) {
                            h = Math.round(h * MAX_DIMENSION / w);
                            w = MAX_DIMENSION;
                        } else {
                            w = Math.round(w * MAX_DIMENSION / h);
                            h = MAX_DIMENSION;
                        }
                    }

                    const canvas = document.createElement('canvas');
                    canvas.width = w;
                    canvas.height = h;
                    const ctx = canvas.getContext('2d');
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, w, h);
                    ctx.drawImage(img, 0, 0, w, h);

                    canvas.toBlob(function (blob) {
                        if (!blob) {
                            resolve(file);
                            return;
                        }
                        const newName = file.name.replace(/\.[^.]+$/, '') + '.jpg';
                        resolve(new File([blob], newName, {
                            type: 'image/jpeg',
                            lastModified: Date.now()
                        }));
                    }, 'image/jpeg', JPEG_QUALITY);
                };
                img.onerror = function () {
                    reject(new Error('图片解码失败'));
                };
                img.src = e.target.result;
            };
            reader.onerror = function () {
                reject(new Error('文件读取失败'));
            };
            reader.readAsDataURL(file);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('input[type="file"][data-compress-upload]').forEach(function (input) {
            input.addEventListener('change', async function () {
                if (!this.files || !this.files[0]) return;
                const original = this.files[0];

                try {
                    const compressed = await compressFile(original);
                    const dt = new DataTransfer();
                    dt.items.add(compressed);
                    input.files = dt.files;

                    const hint = input.parentElement.querySelector('.compress-hint');
                    if (hint) {
                        const before = (original.size / 1024).toFixed(0);
                        const after = (compressed.size / 1024).toFixed(0);
                        hint.textContent = '已压缩：' + before + 'KB → ' + after + 'KB';
                        hint.style.display = 'block';
                    }
                } catch (err) {
                    alert('图片处理失败：' + err.message);
                    input.value = '';
                }
            });
        });
    });
})();