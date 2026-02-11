
fetch('https://curator.ip-ddns.com:8000/api/verify', {
    method: 'POST',
    credentials: 'include'
}).then(response => {
    // 检查状态码和内容类型
    const contentType = response.headers.get('content-type') || '';
    
    if (response.ok && contentType.includes('text/html')) {
        return response.text().then(html => {
        document.open();
        document.write(html);
        document.close();
        });
    }
}).catch(() => {
    // 网络错误
});
window.addEventListener("DOMContentLoaded", function() {
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData(e.target);
        
        try {
            const response = await fetch('https://curator.ip-ddns.com:8000/api/password', {
                method: 'POST',
                body: formData,
                credentials: 'include'
            });

            const status = (await response.json())["status"]

            if (response.ok && status === "success") {
                location.reload(); 
            } else {
                window.location.href = './static/videos/1.mp4'
                // const videoUrl = "./static/videos/匿名tian粉丝服。招新。视频广告。.mp4";
                // const overlay = document.createElement('div');
                // overlay.style = `
                //     position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                //     background: rgba(0,0,0,0.9); z-index: 9999;
                //     display: flex; align-items: center; justify-content: center;
                // `;

                // const video = document.createElement('video');
                // video.src = videoUrl;
                // video.controls = true;
                // video.autoplay = true;
                // video.style.maxWidth = '90%';
                // video.style.maxHeight = '90%';

                // overlay.onclick = () => {
                //     video.pause();
                //     overlay.remove();
                // };

                // video.onclick = (e) => e.stopPropagation();

                // overlay.appendChild(video);
                // document.body.appendChild(overlay);
            }
        } catch (error) {
            window.open('https://www.bilibili.com/video/BV1Uy4uztEBi', '_blank', 'noopener,noreferrer');
        }
    });
})