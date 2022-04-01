function sendIdentifier() {
    let appid = document.getElementById("appid").value;
    let username = document.getElementById("username").value;
    let apiKey = document.getElementById("pwd").value;
    let data = {"appid" : appid, "username" : username, "api-key" : apiKey}
    fetch(url="/api-backend/config_app",{
        method: 'POST',
        headers: {
          'Content-Type': 'application/json;charset=utf-8'
        },
        body: JSON.stringify(data)
    });
};

function deleteEndDevice(end_device) {
    let data = { "end-device" : end_device}
    fetch(url="/api-backend/remove_device",{
        method: 'POST',
        headers: {
          'Content-Type': 'application/json;charset=utf-8'
        },
        body: JSON.stringify(data)
    });
    document.getElementById("end-device-list").removeChild(document.getElementById(end_device))
}

function addEndDevice() {
    let error_msg = document.getElementById("duplicate-error");
    error_msg.setAttribute("hidden","true");
    let end_device = document.getElementById("end-device-id").value;
    let data = { "end-device" : end_device}
    fetch(url="/api-backend/add_device",{
        method: 'POST',
        headers: {
          'Content-Type': 'application/json;charset=utf-8'
        },
        body: JSON.stringify(data)
    }).then(res => {
        if(res.ok) {
            let row = document.createElement("li");
            row.setAttribute("id",end_device);
            let label = document.createElement("p");
            label.textContent = end_device;
            let button = document.createElement("button");
            button.setAttribute("onclick", "deleteEndDevice('"+ end_device + "')");
            button.textContent = "X";
            row.appendChild(label);
            row.appendChild(button);
            document.getElementById("end-device-list").appendChild(row);
        } else {
            error_msg.removeAttribute("hidden","true");
        }
    });
}