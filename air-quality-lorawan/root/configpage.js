function triggerChangeSFX(x) {
    let data_type = document.getElementById("data_type_sf" + x);
    let data_interval =  document.getElementById("data_interval_sf" + x);
    let recovery_interval =  document.getElementById("recovery_interval_sf" + x);
    for(let option of data_interval.children) {
        if(option.value != -1) {
            let disabled = isDisabled(x,data_type.value,data_interval.value,2,option);
            if(disabled) {
                option.setAttribute("disabled","true");
                if(option.value == data_interval.value) {
                    data_interval.value = -1;
                }
            }else {
                option.removeAttribute("disabled");
            }
        }
    }
    for(let option of recovery_interval.children) {
        if(option.value != -1) {
            let disabled = isDisabled(x,data_type.value,data_interval.value,3,option);
            if(disabled) {
                option.setAttribute("disabled","true");
                if(option.value == recovery_interval.value) {
                    recovery_interval.value = -1;
                }
            }else {
                option.removeAttribute("disabled");
            }
        }
    }
}

function isDisabled(sf, data_type, data_interval, option_type, option) {
    switch(sf) {
        case("7"):
            if(data_type == 3 && data_interval == 5 && option_type == 3 && option.value < 4) {
                return true;
            }
            break;
        case("8"):
        if(option_type == 2 && option.value < 10) {
            return true;
        }
        if(data_type == 3 && data_interval == 10 && option_type == 3 && option.value < 4) {
                return true;
            }
            break;
        case("9"):
            if(option_type == 2 && option.value < 10) {
                return true;
            }
            switch(data_type) {
                case("1"):
                    if(option_type == 3 && data_interval <= 10 && option.value < 1000) {
                        return true;
                    }
                    break;
                case("2"):
                case("3"):
                    if(option_type == 2 && option.value < 15) {
                        return true;
                    }
                    if(option_type == 3 && data_interval <= 15 && option.value < 4) {
                        return true;
                    }
                    break;
            }
            break;
        case("10"):
            if(option_type == 2 && option.value < 20) {
                return true;
            }
            switch(data_type) {
                case("1") :
                    if(option_type == 3 && data_interval == 20 && option.value < 16) {
                        return true;
                    }
                    break;
                case("2") :
                    if(option_type == 3 && data_interval == 20 && option.value < 1000) {
                        return true;
                    }
                    if(option_type == 3 && data_interval == 30 && option.value < 4) {
                        return true;
                    }
                    break;
                case("3") :
                    if(option_type == 2 && option.value < 30) {
                        return true;
                    }
                    if(option_type == 3 && data_interval <= 30 && option.value < 4) {
                        return true;
                    }
                    break;
            }
            break;
        case("11"):
            if(option_type == 2 && option.value < 45) {
                return true;
            }
            switch(data_type) {
                case("1") :
                    if(option_type == 3 && data_interval == 45 && option.value < 8) {
                        return true;
                    }
                    break;
                case("2") :
                    if(option_type == 3 && data_interval == 45 && option.value < 32) {
                        return true;
                    }
                    if(option_type == 3 && data_interval == 60 && option.value < 4) {
                        return true;
                    }
                    break;
                case("3") :
                    if(option_type == 2 && option.value < 60) {
                        return true;
                    }
                    if(option_type == 3 && data_interval <= 60 && option.value < 4) {
                        return true;
                    }
                    break;
            }
            break;
        case("12"):
            if(option_type == 2 && option.value < 120) {
                return true;
            }
            if(data_type == 3 && option_type == 3 && option.value < 4) {
                return true;
            }
            break;
    }
    return false;
}

function checkAllFilled() {
    for(let i = 7; i <= 12; i++) {
        let data_type = document.getElementById("data_type_sf" + i);
        let data_interval = document.getElementById("data_interval_sf" + i);
        let recovery_interval = document.getElementById("recovery_interval_sf" + i);
        if(data_type.value == -1 || data_interval.value == -1 || recovery_interval.value == -1){
            return false;
        }
    }
    return true;
}

function sendConfig() {
    let error = document.getElementById("incomplete-error");
    error.setAttribute("hidden","true");
    if(!checkAllFilled()) {
        error.removeAttribute("hidden");
        return;
    }
    let data = {
        "sf7" : {
            "data_type" : parseInt(document.getElementById("data_type_sf7").value),
            "data_interval" : parseInt(document.getElementById("data_interval_sf7").value),
            "data_recovery" : parseInt(document.getElementById("recovery_interval_sf7").value)
        },
        "sf8" : {
            "data_type" : parseInt(document.getElementById("data_type_sf8").value),
            "data_interval" : parseInt(document.getElementById("data_interval_sf8").value),
            "data_recovery" : parseInt(document.getElementById("recovery_interval_sf8").value)
        },
        "sf9" : {
            "data_type" : parseInt(document.getElementById("data_type_sf9").value),
            "data_interval" : parseInt(document.getElementById("data_interval_sf9").value),
            "data_recovery" : parseInt(document.getElementById("recovery_interval_sf9").value)
        },
        "sf10" : {
            "data_type" : parseInt(document.getElementById("data_type_sf10").value),
            "data_interval" : parseInt(document.getElementById("data_interval_sf10").value),
            "data_recovery" : parseInt(document.getElementById("recovery_interval_sf10").value)
        },
        "sf11" : {
            "data_type" : parseInt(document.getElementById("data_type_sf11").value),
            "data_interval" : parseInt(document.getElementById("data_interval_sf11").value),
            "data_recovery" : parseInt(document.getElementById("recovery_interval_sf11").value)
        },
        "sf12" : {
            "data_type" : parseInt(document.getElementById("data_type_sf12").value),
            "data_interval" : parseInt(document.getElementById("data_interval_sf12").value),
            "data_recovery" : parseInt(document.getElementById("recovery_interval_sf12").value)
        },
    };
    fetch(url="/api-backend/config_device",{
        method: 'POST',
        headers: {
          'Content-Type': 'application/json;charset=utf-8'
        },
        body: JSON.stringify(data)
    });
}

function onload() {
    triggerChangeSFX("7");
    triggerChangeSFX("8");
    triggerChangeSFX("9");
    triggerChangeSFX("10");
    triggerChangeSFX("11");
    triggerChangeSFX("12");
}