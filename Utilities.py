import os
import base64

def generate_hoverable_image_buttons(image_folder, image_list, preview_width=300, preview_height=225):
    html_buttons = ""

    for image_name in image_list:
        image_path = os.path.join(image_folder, image_name).replace("\\", "/")
        with open(image_path, "rb") as img_file:
            encoded_image = base64.b64encode(img_file.read()).decode()

        html_buttons += f"""
        <div class="hover-img-button" style="display:inline-block; margin:20px; text-align:center;">
            <button 
                class="img-btn"
                data-img="data:image/png;base64,{encoded_image}"
                data-name="{image_name}"
                style="margin-bottom:5px; cursor:pointer;"
            >{image_name}</button>
        </div>
        """

    hover_css_and_script = f"""
    <style>
    #img-preview {{
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        display: none;
        z-index: 9999;
        border: 2px solid #ccc;
        background: white;
        padding: 6px;
        box-shadow: 0 0 8px rgba(0,0,0,0.3);
        text-align: center;
    }}
    </style>

    <div id="img-preview">
        <img id="preview-img" src="" width="{preview_width}" height="{preview_height}" />
        <div id="preview-label" style="font-size:14px; margin-top:4px;"></div>
    </div>

    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        const buttons = document.querySelectorAll('.img-btn');
        const preview = document.getElementById('img-preview');
        const previewImg = document.getElementById('preview-img');
        const previewLabel = document.getElementById('preview-label');

        buttons.forEach(btn => {{
            btn.addEventListener('mouseover', () => {{
                previewImg.src = btn.dataset.img;
                previewLabel.innerText = btn.dataset.name;
                preview.style.display = 'block';
            }});
            btn.addEventListener('mouseout', () => {{
                preview.style.display = 'none';
            }});
            btn.addEventListener('click', () => {{
                const imgName = btn.dataset.name;
                const url = new URL(window.location.href);
                url.searchParams.set("selected", imgName);
                window.location.href = url.toString();
            }});
        }});
    }});
    </script>
    """

    return hover_css_and_script + html_buttons




# def generate_hoverable_image_buttons(image_folder, image_list, preview_width=300, preview_height=225):
#     html_buttons = ""
#
#     for image_name in image_list:
#         image_path = os.path.join(image_folder, image_name).replace("\\", "/")
#         with open(image_path, "rb") as img_file:
#             encoded_image = base64.b64encode(img_file.read()).decode()
#
#         html_buttons += f"""
#         <div class="hover-img-button" style="display:inline-block; margin:20px; text-align:center;">
#             <button
#                 class="img-btn"
#                 data-img="data:image/png;base64,{encoded_image}"
#                 data-name="{image_name}"
#                 style="margin-bottom:5px;"
#             >{image_name}</button>
#         </div>
#         """
#
#     hover_css_and_script = f"""
#     <style>
#     #img-preview {{
#         position: fixed;
#         top: 50%;
#         left: 50%;
#         transform: translate(-50%, -50%);
#         display: none;
#         z-index: 9999;
#         border: 2px solid #ccc;
#         background: white;
#         padding: 6px;
#         box-shadow: 0 0 8px rgba(0,0,0,0.3);
#         text-align: center;
#     }}
#     .img-btn {{
#         padding: 10px;
#         cursor: pointer;
#         background-color: #4CAF50;
#         color: white;
#         border: none;
#         border-radius: 5px;
#     }}
#     .img-btn:hover {{
#         background-color: #45a049;
#     }}
#     </style>
#
#     <div id="img-preview">
#         <img id="preview-img" src="" width="{preview_width}" height="{preview_height}" />
#         <div id="preview-label" style="font-size:14px; margin-top:4px;"></div>
#     </div>
#
#     <script>
#     document.addEventListener("DOMContentLoaded", function() {{
#         const buttons = document.querySelectorAll('.img-btn');
#         const preview = document.getElementById('img-preview');
#         const previewImg = document.getElementById('preview-img');
#         const previewLabel = document.getElementById('preview-label');
#
#         buttons.forEach(btn => {{
#             btn.addEventListener('mouseover', () => {{
#                 previewImg.src = btn.dataset.img;
#                 previewLabel.innerText = btn.dataset.name;
#                 preview.style.display = 'block';
#             }});
#             btn.addEventListener('mouseout', () => {{
#                 preview.style.display = 'none';
#             }});
#             btn.addEventListener('click', () => {{
#                 window.location.href = window.location.href.split('?')[0] + '?selected=' + btn.dataset.name;
#             }});
#         }});
#     }});
#     </script>
#     """
#
#     return hover_css_and_script + html_buttons


# def generate_hoverable_image_buttons(image_folder, image_list, preview_width=300, preview_height=225):
#     html_buttons = ""
#
#     for image_name in image_list:
#         image_path = os.path.join(image_folder, image_name).replace("\\", "/")
#         with open(image_path, "rb") as img_file:
#             encoded_image = base64.b64encode(img_file.read()).decode()
#
#         html_buttons += f"""
#         <div class="hover-img-button" style="display:inline-block; margin:20px; text-align:center;">
#             <button
#                 class="img-btn"
#                 data-img="data:image/png;base64,{encoded_image}"
#                 data-name="{image_name}"
#                 style="margin-bottom:5px;"
#                 onclick="window.location.href = '?selected={image_name}'"
#             >{image_name}</button>
#         </div>
#         """
#
#     hover_css_and_script = f"""
#     <style>
#     #img-preview {{
#         position: fixed;
#         left: 50%;
#         bottom: 0;
#         transform: translateX(-50%);
#         display: none;
#         z-index: 9999;
#         border: 2px solid #ccc;
#         background: white;
#         padding: 6px;
#         box-shadow: 0 0 8px rgba(0,0,0,0.3);
#         text-align: center;
#     }}
#     </style>
#
#     <div id="img-preview">
#         <img id="preview-img" src="" width="{preview_width}" height="{preview_height}" />
#         <div id="preview-label" style="font-size:14px; margin-top:4px;"></div>
#     </div>
#
#     <script>
#     document.addEventListener("DOMContentLoaded", function() {{
#         const buttons = document.querySelectorAll('.img-btn');
#         const preview = document.getElementById('img-preview');
#         const previewImg = document.getElementById('preview-img');
#         const previewLabel = document.getElementById('preview-label');
#
#         buttons.forEach(btn => {{
#             btn.addEventListener('mouseover', () => {{
#                 previewImg.src = btn.dataset.img;
#                 previewLabel.innerText = btn.dataset.name;
#                 preview.style.display = 'block';
#             }});
#             btn.addEventListener('mouseout', () => {{
#                 preview.style.display = 'none';
#             }});
#         }});
#     }});
#     </script>
#     """
#
#     return hover_css_and_script + html_buttons


