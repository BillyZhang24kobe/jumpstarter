var dc_answerNames = document.getElementById("dropdown-content-answerNames");
var modal = document.getElementById("myModal");
var modal_breakdown = document.getElementById("myModal-breakdown");
var modal_ccd = document.getElementById("myModal-context-curation-draft");
var modal_ced = document.getElementById("myModal-context-elicitation-draft");

var modal_span = document.getElementsByClassName("close")[0];
var modal_breakdown_span = document.getElementById("myModal-brkdwn-close");
var modal_ccd_span = document.getElementById("myModal-ccd-close");
var modal_ced_span = document.getElementById("myModal-ced-close");
modal_span.onclick = function() {
    modal.style.display = "none";
}
modal_breakdown_span.onclick = function() {
    modal_breakdown.style.display = "none";
}
modal_ccd_span.onclick = function() {
    modal_ccd.style.display = "none";
}
modal_ced_span.onclick = function() {
    modal_ced.style.display = "none";
}

window.onclick = function(event) {
    if (event.target == modal) {
        modal.style.display = "none";
    }
    if (event.target == dc_answerNames) {
      dc_answerNames.style.display = "none";
    }
    if (event.target == modal_breakdown) {
      modal_breakdown.style.display = "none";
    }
    if (event.target == modal_ccd) {
      modal_ccd.style.display = "none";
    }
    if (event.target == modal_ced) {
      modal_ced.style.display = "none";
    }
}

function get_general_steps(query_id){         
    let query = $("#"+query_id).val()
    
    let data = {"query": query}
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/get_general_steps",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("get general steps")
            console.log(data)  
            let response = data["response"]
            var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
            var formattedSteps = '';

            // Remove the first empty string if it's there because of split at the beginning of the text
            if (steps[0] === '') {
                steps.shift();
            }

            // Map each step to a list item
            var formattedSteps = steps.map(function(step) {
                return '<li>' + step.trim() + '</li>'; // Trim each step and wrap it in <li> tags
            }).join(''); // Join all list items into a single string

            $("#results-"+query_id).html('<ul>' + formattedSteps + '</ul>');
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    })
}

function get_detailed_steps(query_id){
    // query 2: generate detailed steps
    let query = $("#"+query_id).val()        
    let data = {"query":query}
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/get_detailed_steps",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("get detailed steps")
            console.log(data)  
            let response = data["response"]
            var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
            var formattedSteps = '';

            // Remove the first empty string if it's there because of split at the beginning of the text
            if (steps[0] === '') {
                steps.shift();
            }

            // Map each step to a list item
            var formattedSteps = steps.map(function(step) {
                // Find the index of the first semicolon
                var semicolonIndex = step.indexOf(':');
                if (semicolonIndex !== -1) {
                    // Split the step into two parts and bold the first
                    return '<li><strong>' + step.substring(0, semicolonIndex + 1) + '</strong>' + step.substring(semicolonIndex + 1) + '</li>';
                } else {
                    // If there is no semicolon, return the step as is
                    return '<li>' + step + '</li>';
                }
                // return '<li>' + step.trim() + '</li>'; // Trim each step and wrap it in <li> tags
            }).join(''); // Join all list items into a single string
            
            $("#results-"+query_id).html('<ul>' + formattedSteps + '</ul>');

        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    })
}

function get_emotional_support(query_id){
    let query = $("#"+query_id).val()
    let data = {"query":query}
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/get_emotional_support",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("get emotional support")
            console.log(data)  
            let response = data["response"]
            var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
            var formattedSteps = '';

            // Remove the first empty string if it's there because of split at the beginning of the text
            if (steps[0] === '') {
                steps.shift();
            }

            // Map each step to a list item
            var formattedSteps = steps.map(function(step) {
                return '<li>' + step.trim() + '</li>'; // Trim each step and wrap it in <li> tags
            }).join(''); // Join all list items into a single string

            $("#results-"+query_id).html('<ul>' + formattedSteps + '</ul>');
            
            // replace new lines with <br> tags
            // response = response.replace(/\n/g, "<br>");
            // $("#results-"+query_id).html(response);
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    })
}

function get_timeline(query_id){
    let query = $("#"+query_id).val()
    let data = {"query":query}
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/get_detailed_steps",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("get timeline")
            console.log(data)  
            let response = data["response"]
            var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
            var formattedSteps = '';

            // Remove the first empty string if it's there because of split at the beginning of the text
            if (steps[0] === '') {
                steps.shift();
            }

            // Map each step to a list item
            var formattedSteps = steps.map(function(step) {
                // Find the index of the first semicolon
                var semicolonIndex = step.indexOf(':');
                if (semicolonIndex !== -1) {
                    // Split the step into two parts and bold the first
                    return '<li><strong>' + step.substring(0, semicolonIndex + 1) + '</strong>' + step.substring(semicolonIndex + 1) + '</li>';
                } else {
                    // If there is no semicolon, return the step as is
                    return '<li>' + step + '</li>';
                }
                // return '<li>' + step.trim() + '</li>'; // Trim each step and wrap it in <li> tags
            }).join(''); // Join all list items into a single string
            
            $("#results-"+query_id).html('<ul>' + formattedSteps + '</ul>');

            // $("#results-query1").html('<ul>' + formattedSteps + '</ul>');
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    })
}

// JavaScript to make radio buttons cancellable
let currentRadio = null;

// function checkRadio(radio) {
//     if (radio === currentRadio) {
//         currentRadio = null;
//         radio.checked = false;
//     } else {
//         currentRadio = radio;
//     }
// }

let inputCount = 1;
function addInputGroup() {
    inputCount++;
    let newInputGroup = `
        <div class="search-section" id="ss-${inputCount}">
            <textarea type="text" id="query${inputCount}" placeholder="Type your query..." oninput="displayCommandButtons()" rows="3" cols="50"></textarea><br>
            <div class="command-buttons" id="cb-${inputCount}" style="display:none;">
                <button id="cb-${inputCount}-steps" onclick="general_steps('query${inputCount}')">Show me the steps</button>
                <button id="cb-${inputCount}-support" onclick="emotional_support('query${inputCount}')">Ask for emotional support</button>
                <button id="cb-${inputCount}-reminder" onclick="reminder('query${inputCount}')">Set up a reminder</button>
                <button id="cb-${inputCount}-draft" onclick="write_draft('query${inputCount}')">Write a draft</button>
            </div>
            <input type="submit" class="submit-query" id="submit_query_button_${inputCount}" value="Submit" onclick="get_started()">
            <div class="results-box" id="results-query${inputCount}">
            
            </div>
        </div>
    `;
    $("#slider").append(newInputGroup);
    
    // Scroll to the end of the slider container to show the new input
    const slider = document.getElementById('slider');
    slider.scrollLeft = slider.scrollWidth;
}

function createTextarea(step_text_id){
    console.log(step_text_id)
    // take the div of the step_text_id and creae a textarea
    var container = document.getElementById(step_text_id);
    var exsitingTextarea = document.getElementById(step_text_id + "-text");
    if (exsitingTextarea) {
        textarea.classList.toggle('hidden');
    } else {
        textarea = document.createElement("textarea");
        textarea.id = step_text_id + "-text";
        textarea.placeholder = "Type your input here...";
        // textarea.addEventListener("input", updateAnswerDraft);
        container.innerHTML = '';
        container.appendChild(textarea);
        
        // add the new textarea to the container
        // updateAnswerDraft();
    }
}

let currentOption = '';
var currentContentIndex = 0;
var currentLetterIndex = 0;

// user prompt
// var prompt_steps_start = "Please break down the task below into three to six manageable subtasks. \n $sub_goal$ by $deadline$: $description$";
var prompt_steps_start = "Please break down the task below into three to six manageable subtasks. \n $sub_goal$: $description$";
// var prompt_need_help = "My user needs help with the current task $sub_goal$: $description$ by $deadline$.";
var prompt_need_help = "My user needs help with the current task $sub_goal$: $description$.";
var prompt_user_query_steps = "They have a query: Please show me the steps to achieve this goal.";
var prompt_user_query_brainstorm = "They have a query: Please help me do the task.";
var prompt_current_structure = "The existing step structure is shown as follows: $curr_tree_texts$.";
var prompt_current_parent = "Here is the current task structure: $curr_parents$.";
// var prompt_suplemental_steps = "Please directly give the response that fills in the current subtask $sub_goal$ by $deadline$ in the provided task structure.";
var prompt_suplemental_steps = "Please directly give the response that fills in the current subtask $sub_goal$ in the provided task structure.";
// var prompt_format_steps = `Format the response like this: 1. {subtask1 title} by {subtask1 deadline date}: {subtask1 detailed description} 2. {subtask2 title} by {subtask2 deadline date}: {subtask2 detailed description} 3. {subtask3 title} by {subtask3 deadline date}: {subtask3 detailed description} 
// Please use month/day/year format for the deadline date. Please do not include ** in the subtask title. Please directly give the response and do not start with "{current subtask title}:".`;
// var prompt_format_steps = `Format the response like this: 1. {subtask1 title}: {subtask1 detailed description} 2. {subtask2 title}: {subtask2 detailed description} 3. {subtask3 title}: {subtask3 detailed description} 
// Please do not include ** in the subtask title. Please directly give the response and do not start with "{current subtask title}:".`;
var prompt_format_steps = `Format the response like this: 1. [Duration for subtask1] {subtask1 title}: {subtask1 detailed description} 2. [Duration for subtask2] {subtask2 title}: {subtask2 detailed description} 3. [Duration for subtask3] {subtask3 title}: {subtask3 detailed description}.
Please specify the duration for each subtask in terms of days, weeks or months. For example, [1 week], [2-4 weeks], [1 month], and [1-2 months]. Please do not include other text formats for duration such as [Ongoing]. Please do not include ** in the subtask title. Please directly give the response and do not start with "{current subtask title}:"`;
var prompt_user_current_answer = "Their current answer is: $answer_draft$.";
var prompt_finished_previous_step = "They finished a previous step: ";
var prompt_result_previous_step = "This is the result of the previous step: ";
var prompt_user_need_help = "My user needs help with the current task ";

// system prompt
// var sys_prompt_user_info = "My user's background information is as follows: $user_info$.";
var sys_prompt_user_purpose = "My user has a main purpose: $purpose$.";
var sys_prompt_user_purpose_verbose = "My user has a main purpose: ";
var sys_prompt_context_info = "Please consider the following context information from my user: $context$.";

function general_steps(query_id){
    $("#"+query_id).val(prompt_steps);
    currentOption = "steps";
}

function framework_brainstorm(query_id){
    $("#"+query_id).val(prompt_framework_brainstorm);
    currentOption = "framework_brainstorm";
}

function brainstorm(query_id){
    $("#"+query_id).val(prompt_brainstorm);
    currentOption = "brainstorm";
}

function write_draft(query_id){
    $("#"+query_id).val(prompt_draft);
    currentOption = "draft";
}

// show the context window upon clicking the "start drafting" button
function showPrompts(){
    var context_window = document.getElementById('context-window');
    context_window.style.display = 'block';

    // print global user context keys in "context-input" textarea
    var context_input = document.getElementById('context-input');
    context_input.value = printGlobalUserContextKeys();
}

// Function to update the displayed content for a given draft
function updateDisplayedContent(contentDivId, contentIndex) {
    var contentDiv = document.getElementById(contentDivId);
    var textareas = contentDiv.getElementsByTagName('textarea');
    for (var i = 0; i < textareas.length; i++) {
        textareas[i].style.display = 'none';
    }
    if (textareas[contentIndex]) {
        textareas[contentIndex].style.display = 'block';
    }
}

function printCuratedContexts(curated_context_keys) {
    // curated_context_keys: a string of context keys separated by comma
    // split the string by comma and print each key
    var keys = curated_context_keys.split(',');
    output = "";
    for (var i = 0; i < keys.length; i++) {
        if (keys[i] !== '') {
            // remove the leading and trailing quotes: '' or ""
            ctx_name = keys[i].replace(/^['"]|['"]$/g, '');
            output += ctx_name + ": " + user_context[ctx_name] + "\n";
        }
    }
    return output;
}

function printAllLocalUserContexts() {
    allUserContexts = "";
    // check the type of userContext

    if (typeof user_context === 'string') {
        user_context = user_context.replace(/[\u0000-\u001F\u007F]/g, '').replace(/\n/g, '\\n');
        userLocalContext = JSON.parse(user_context);
    } else {
        userLocalContext = user_context;
    }
    
    // iterate over userContext object and print it as a string
    for (var key in userLocalContext) {
        allUserContexts += key + ": " + userLocalContext[key] + "\n";
    }
    return allUserContexts;
}

function printAllGlobalUserContexts() {
    allUserContexts = "";
    console.log("UserGlobalContext: " + userGlobalContext)
    console.log("Type of UserGlobalContext: " + typeof userGlobalContext)

    if (typeof userGlobalContext === 'string') {
        // check the type of userContext
        userGlobalContext = userGlobalContext.replace(/[\u0000-\u001F\u007F]/g, '').replace(/\n/g, '\\n');
        user_global_context = JSON.parse(userGlobalContext);
    } else {
        user_global_context = userGlobalContext;
    }

    userGlobalContext_str = document.getElementById('context-input').value;  // '$Age of the User$, $State or Country$, '
    if (userGlobalContext_str === '') {
        // root node
        Object.keys(user_global_context).forEach(function(key) {
            allUserContexts += key + ": " + user_global_context[key] + "\n";
        });
    } else {
        userGlobalContext_lst = userGlobalContext_str.split(', ');  // ['$Age of the User$', '$State or Country$', '']
        userGlobalContext_lst.forEach(function(key) {
            if (key !== '') {
                key = key.slice(1,-1);  // remove leading and trailing '$' sign
                allUserContexts += key + ": " + user_global_context[key] + "\n";
            }
        });
    }

    // iterate over userContext object and print it as a string
    // Object.keys(user_global_context).forEach(function(key) {
    //     allUserContexts += key + ": " + user_global_context[key] + "\n";
    // });
    return allUserContexts;
}

function printGlobalUserContextKeys() {
    output = "";
    // iterate over userContext object and print its as a string ($key1$, $key2$, ...)
    Object.keys(userGlobalContext).forEach(function(key) {
        output += "$" + key + "$, ";
    });
    return output;
}

function context_elicitation_draft() {
    console.log("In context_elicitation_draft ...")
    task_name = currNode.text;
    task_description = currNode.description;

    document.getElementById('globalFormGroup-ced').innerHTML = `<div class="elicit-draft">
                        <h5>Add your own info</h5>
                        <div class="form-group">
                            <input type="text" id="customName" name="customName" placeholder="Name. E.g. Travel Duration" style="margin-right: 45px">
                            <input type="text" id="customContent" name="customContent" placeholder="Content. E.g. One week."> <span style="margin:5px"> OR </span> 
                            <input type="file" id="customFile" name="customFile">
                        </div>
                    </div>
                    <button class="sd-button" onclick="regenerate(0, 'brainstorm')">Regenerate a new draft</button>`;

    // check if userContext is empty Object
    // if (Object.keys(userContext).length === 0) {
    //     regenerate(0, 'brainstorm');
    // } else {
    let data = {
        "main_purpose": taskInput,
        "task_name": task_name,
        "task_description": task_description,
        "user_context": { ...userGlobalContext, ...user_context }
    }
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/context_elicitation_draft",
        dataType: "json",
        contentType: "application/json; charset=utf-8",
        data: JSON.stringify(data),
        contentType: 'application/json',
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(response, text) {
            console.log('response from context_elicitation_draft: ', response);
            context = response['context'];

            if (context.length > 0) {
                // iterate over the context object and add it to the model -> prepend to the exisitng form
                var ced_header = document.getElementById('ced-header');
                ced_header.innerHTML = `<h5>To get you a better draft, we suggest you providing the following extra info. You can skip them or add your own info.</h5>`;

                const globalFormGroup_ced = document.getElementById('globalFormGroup-ced');
                context.forEach(obj => {
                    const key = obj['name']
                    const question = obj['question']
                    const description = obj['description']

                    const newFormGroup = document.createElement('div');
                    newFormGroup.className = 'form-group';
                    newFormGroup.innerHTML = `
                        <label for="context-input-ced-${key}" title="${description}">${question}</label> <br>
                        <input type="text" id="context-input-ced-${key}" name="context-input-ced-${key}" placeholder="">`;

                    // prepend the new form group to the existing form
                    globalFormGroup_ced.insertBefore(newFormGroup, globalFormGroup_ced.firstChild);
                });
            } else {
                console.log('No context to elicit ... Proceed to generate the draft without using context');
                var ced_header = document.getElementById('ced-header');
                ced_header.innerHTML = `<h5>You seem to have sufficient info to get a decent draft. Feel free to directly regenerate the draft or add any extra info. </h5>`;
            }

            modal_ced.style.display = "block";
        },
        error: function(request, status, error){
            console.log("Error... Proceed to generate the draft without using context");
            console.log(request)
            console.log(status)
            console.log(error)
            regenerate(0, 'brainstorm');
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    });
    // }
}

function context_curation_draft() {
    console.log("In context_curation_draft ...")

    var context_window = document.getElementById('context-window');
    if (context_window.style.display === 'none') {
        context_window.style.display = 'block';
    }

    // empty checkboxlist-ccd
    document.getElementById('checkboxList-ccd').innerHTML = '';

    task_name = currNode.text;
    task_description = currNode.description;
    // check if userContext is empty Object
    if (Object.keys(user_context).length === 0) {
        get_gpt_response();
    } else {
        let data = {
            "main_purpose": taskInput,
            "task_name": task_name,
            "task_description": task_description,
            "user_context": user_context
        }
        console.log(data)
        $.ajax({
            type: "POST",
            url: "/context_curation_draft", 
            dataType: "json",
            contentType: "application/json; charset=utf-8",
            data: JSON.stringify(data),
            contentType: 'application/json',
            beforeSend: function () { 
                $("#spinner-div").show()
            },
            success: function(data, text) {
                console.log(data);
                modal_ccd.style.display = "block";

                emptyAllContextInputs();

                context = data['context'];  // a list of strings

                // iterate over the list and append the context name and its checkbox to the div with id 'checkboxList-ccd'
                const checkboxList = document.getElementById('checkboxList-ccd');
                for (var i = 0; i < context.length; i++) {
                    var checkbox = document.createElement('div');
                    checkbox.className = 'checkbox';
                    checkbox.innerHTML = '<input type="checkbox" id="checkbox-ccd-' + context[i] + '" name="context-"' + context[i] + ' value="' + context[i] + '" checked><label for="checkbox-ccd-' + context[i] + '">' + context[i] + '</label>';
                    checkboxList.appendChild(checkbox);
                }

                // Only display the keys that are not in context in userContext
                var dropdown_content_ccd = document.getElementById('dropdown-content-answerNames-ccd');
                Object.keys(user_context).forEach(function(key) {
                    if (!context.includes(key)) {
                        var newDropDownitem = document.createElement('div');
                        newDropDownitem.className = 'dropdown-content-items';
                        newDropDownitem.innerHTML = `<a onclick="showContextKeys('` + `${key}` + `')" title="${user_context[key]}">${key}</a>`;
                        dropdown_content_ccd.appendChild(newDropDownitem);
                    }
                });
                // for (var key in user_context) {
                //     if (!context.includes(key)) {
                //         var newDropDownitem = document.createElement('div');
                //         newDropDownitem.className = 'dropdown-content-items';
                //         newDropDownitem.innerHTML = `<a onclick="showContextKeys('` + `${key}` + `')" title="${user_context[key]}">${key}</a>`;
                //         dropdown_content_ccd.appendChild(newDropDownitem);
                //     }
                // }
            },
            error: function(request, status, error){
                console.log("Error... Proceed to generate the draft without using context");
                console.log(request)
                console.log(status)
                console.log(error)
                get_gpt_response();
            },
            complete: function () { 
                $("#spinner-div").hide()
            },
        });
    }
}

function context_curation_breakdown(task_name, task_description) {
    console.log("In context_curation_breakdown ...")
    let data = {
            "main_purpose": taskInput,
            "task_name": task_name,
            "task_description": task_description,
            "user_context": user_context
    }
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/context_curation_breakdown",
        dataType: "json",
        contentType: "application/json; charset=utf-8",
        data: JSON.stringify(data),
        contentType: 'application/json',
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text) {
            console.log(data);
            modal_breakdown.style.display = "block";
        },
        error: function(request, status, error){
            console.log("Error... Proceed with normal step node");
            console.log(request)
            console.log(status)
            console.log(error)
            get_steps();
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    });
}

function get_steps(select_first_node=false) {
    currentOption = "steps";
    modal.style.display = "none";
    modal_breakdown.style.display = "none";
    get_started_all(select_first_node);
}

function get_fork_steps() {
    console.log("In get_fork_steps ...")

    var userInput = document.getElementById("context-input-fork").value;
    console.log("User input: " + userInput);
    modal.style.display = "none";

    const context = userInput;
    const description = `${currNode.description}`;
    const duration = `${currNode.duration}`;
    // const context = userInput;

    let data = {"context": context, "description": description, "duration": duration}
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/get_fork_steps",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("get fork steps")
            console.log(data)  
            let response = data["response"]
            let context_descriptions = data["descriptions"]
            let fork_duration = data["duration"]
            createForkNodes(response, context_descriptions, fork_duration);
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        },
    })
}

// function get_fork_steps() {
//     // console.log("In get_fork_steps ...")
//     const context = document.getElementById('context-input').value;

//     if (context === '') {
//         console.log('This is a normal step node ...');
//         get_steps()
//     } else {
//         console.log('This is a fork node ...');
//         modal.style.display = "block"; 
//     }
// }

function get_gpt_response() {
    // hide the modal for modal_ccd
    modal_ccd.style.display = "none";

    currentOption = "brainstorm";
    // hide startButtonContainer
    document.getElementById('startButtonContainer').style.display = 'none';
    document.getElementById('regenButtonContainer').style.display = 'block';
    get_started_all();
}

function acceptSteps(steps) {
    // Accept the steps and expand the tree
    console.log("In acceptSteps ...")
    console.log(steps)
    
    // iterate through the steps and create child nodes for current node
    for (var i = 0; i < steps.length; i++) {
        var step = steps[i];
        var stepid = i;
        // take only the step texts before ':'
        var stepText = step.split(":")[0];  // [1 week] Assess Convenience and Budget
        console.log("Step text in acceptSteps: " + stepText)

        // split the duration from the step text
        var duration = stepText.split("]")[0].slice(1);  // 1 week
        var nodeText = stepText.split("]")[1].trim();  // Assess Convenience and Budget

        // if (stepText.includes('by')) {
        //     var deadline = stepText.split('by')[1].trim()
        //     var nodeText = stepText.split('by')[0].trim()
        // } else {
        //     var deadline = '';
        //     var nodeText = stepText.trim();
        // }
        var deadline = ''
        // var nodeText = stepText.trim();
        var descriptions = step.split(":")[1];

        if (currNode.id === '0-1-0-0') { // output to overview for root node
            var desc = document.getElementById("desc");
            // append the step text to the description
            desc.innerHTML += "<h5>" + "<b>" + nodeText + ` (${duration})` +  "</b>" + "</h5>" + "<h6>" + descriptions + "</h6>" +  "<br>";
            currNode.description += "<h5>" + "<b>" + nodeText + ` (${duration})` +  "</b>" + "</h5>" + "<h6>" + descriptions + "</h6>" +  "<br>";
        }

        // Subtask Detection: Detect if the current node (node text + descriptions) needs to be broken down into subtasks
        var need_subtasks = false;
        let data = {"node_text": nodeText, "description": descriptions}
        console.log(data)
        $.ajax({
            type: "POST",
            url: "/detect_subtasks",
            dataType : "json",
            contentType: "application/json; charset=utf-8",
            data : JSON.stringify(data),
            async: false,
            success: function(data, text){
                console.log("In detect subtasks ... ")
                console.log(data)  
                response = data["response"];
                if (response === 'yes' || response === 'Yes') {
                    need_subtasks = true;
                }
                console.log("need subtasks for node " + nodeText + ": " + need_subtasks)
            },
            error: function(request, status, error){
                console.log("Error");
                console.log(request)
                console.log(status)
                console.log(error)
            },
        })

        var new_level = currNode.level + 1;
        // var nodeId = `${new_level}-${currNode.step_id}-${stepid}`;
        var nodeId = `${Object.keys(nodeMap).length}-${new_level}-${currNode.step_id}-${stepid}`

        const newNode = new TreeNode(nodeId, nodeText, stepid, new_level, currNode.id, desc=descriptions, deadline=deadline, need_subtasks=need_subtasks, duration=duration);
        currNode.addChild(newNode);
        addNodeToMap(newNode);
    }
    showChildren(currNode);
    checkProgress(currNode);
}

// Function to regenerate the output for the selected action
function regenerate(index, action, regen=false) {
    console.log("In regenerate ..." + index)

    // hide the ced modal
    modal_ced.style.display = "none";

    // TODO: update userContext if new context is added
    if (!regen) {
        updateUserContext(currNode);
    }

    if (action == 'steps') {
        currNode.gpt_response_steps[0].response = '';  // empty current response in based on index 
    } else {
        currNode.gpt_response_brainstorm[0].response = '';  // empty current response in based on index

    }

    // construct system prompts
    let sys_prompt = '';
    // if (filenames) {
    //     sys_prompt += sys_prompt_user_info + '\n' + sys_prompt_user_purpose
    // } else {
    //     sys_prompt += sys_prompt_user_purpose
    // }
    sys_prompt += sys_prompt_user_purpose

    // get current tree structure in plain text
    let treeTexts = generateTreeString(nodeMap['level-0-1-0-0']);

    // get parent nodes of the current node
    let parentNodeTexts = generateParentString(currNode);

    // get the value of the textarea
    const purpose = document.getElementById('purpose').innerText;
    const query = document.getElementById('prompt').value;
    // const query = prompt_current_parent + '\n' + document.getElementById('prompt').value;
    const curr_action = action;
    const sub_goal = `${currNode.text}`;
    const answer_draft = $("#answer-draft").val();
    // const prev_answer_draft = prevNodeAnswerDraft;
    const currTreeTexts = treeTexts;
    const currParentNodeTexts = parentNodeTexts;
    const deadline = `${currNode.deadline}`;
    const description = `${currNode.description}`;
    var context = printAllGlobalUserContexts();
    console.log("AllGlobalUserContext: ", context);
    
    // document.getElementById('context-input').value;

    // add global context by default
    // context += printAllGlobalUserContexts();

    if (currNode.curated_context_draft !== '') {
        context += currNode.curated_context_draft;
    }

    let jsonData = {
        "query":query, "purpose":purpose, "action":curr_action, "sub_goal":sub_goal, "answer_draft":answer_draft, "curr_tree_texts": currTreeTexts, "curr_parents": currParentNodeTexts, "deadline": deadline, "description": description, "filenames": filenames, "context": context, "sys_prompt": sys_prompt
    }

    console.log(jsonData)

    // Append JSON data as a string under a single key
    // formData.append('jsonData', JSON.stringify(jsonData));
    $.ajax({
        type: "POST",
        url: "/get_started",
        // processData: false,
        // contentType: false,          
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(jsonData),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("In regenerate ...")
            console.log(data)
            let response = data["response"]
            if (action == 'steps') {
                // document.getElementById('steps').innerHTML = '';
                // document.getElementById('steps_output').innerHTML = '';
                currNode.gpt_response_steps[index].response = response;
                showActionResults(response, index, query, action);
            } else if (action == 'brainstorm') {
                document.getElementById('brainstorm').innerHTML = '';
                document.getElementById('brainstorm_output').innerHTML = '';
                currNode.gpt_response_brainstorm[index].response = response;
                showActionResults(response, index, query, action);
            } 
            // else if (index == 2) {
            //     document.getElementById('draft').innerHTML = '';
            //     document.getElementById('draft_output').innerHTML = '';
            // }
            // document.getElementById('output').innerHTML = '';
            

            // currNode.gpt_response_all[index].response = response;
            // showActionResults(response, index, query, action);
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        }
    })
}

// Handlers for the regenerate, previous, and next buttons
function reg_draft(index) {
// document.getElementById('regenerate').addEventListener('click', function() {
    // Regenerate a new draft and append it to the response_ structure
    var regQuery = document.getElementById('reg-query').value;
    // if (currentOption == 'brainstorm') {
    var currDraft = document.getElementById('content_brainstorm'+ currentLetterIndex + '_textarea' + currentContentIndex).value;
    // } 
    // else if (index == 2) {
    //     var currDraft = document.getElementById('content_draft'+ currentLetterIndex + '_textarea' + currentContentIndex).value;
    // }
    let data = {"query":regQuery, "draft":currDraft}
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/regenerate",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("regenerate")
            console.log(data)  
            let response = data["response"]
            // let prompt = data["prompt"]
            // document.getElementById("prompt-c").innerHTML = prompt;

            // }
            // append the new draft to the current letter
            if (typeof currNode.gpt_response[currentLetterIndex] === 'string') {
                currNode.gpt_response.push(response);
                var newContentIndex = currNode.gpt_response.length - 1;
            } else {
                currNode.gpt_response[currentLetterIndex].content.push(response);
                var newContentIndex = currNode.gpt_response[currentLetterIndex].content.length - 1;
            }

            currentContentIndex = newContentIndex;

            if (currentOption == 'brainstorm') {
                // show the new draft in current content div
                var newTextArea = document.createElement('textarea');
                newTextArea.id = 'content_brainstorm' + currentLetterIndex + "_textarea" + newContentIndex;
                newTextArea.value = response;
                newTextArea.rows = 10;
                document.getElementById('content_brainstorm' + currentLetterIndex).appendChild(newTextArea);
                
                updateDisplayedContent('content_brainstorm' + currentLetterIndex, newContentIndex);
            } 
            // else if (index == 2) {
            //     // show the new draft in current content div
            //     var newTextArea = document.createElement('textarea');
            //     newTextArea.id = 'content_draft' + currentLetterIndex + "_textarea" + newContentIndex;
            //     newTextArea.value = response;
            //     newTextArea.rows = 5;
            //     document.getElementById('content_draft' + currentLetterIndex).appendChild(newTextArea);
                
            //     updateDisplayedContent('content_draft' + currentLetterIndex, newContentIndex);
            // }
            // // show the new draft in current content div
            // var newTextArea = document.createElement('textarea');
            // newTextArea.id = 'content_draft' + currentLetterIndex + "_textarea" + newContentIndex;
            // newTextArea.value = response;
            // newTextArea.rows = 5;
            // document.getElementById('content_draft' + currentLetterIndex).appendChild(newTextArea);
            
            // updateDisplayedContent('content_draft' + currentLetterIndex, newContentIndex);
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        }
    })
}

function show_prev_draft() {
    // Navigate to the previous content draft if possible
    if (currentContentIndex > 0) {
        currentContentIndex--;
        updateDisplayedContent('content_brainstorm' + currentLetterIndex, currentContentIndex);
    }
}

function show_next_draft() {
    // Navigate to the next content draft if possible
    if (typeof currNode.gpt_response[currentLetterIndex] === 'string') {
        if (currentContentIndex < currNode.gpt_response.length - 1) {
            currentContentIndex++;
            updateDisplayedContent('content_brainstorm' + currentLetterIndex, currentContentIndex);
        }
    } else {
        if (currentContentIndex < currNode.gpt_response[currentLetterIndex].content.length - 1) {
            currentContentIndex++;
            updateDisplayedContent('content_brainstorm' + currentLetterIndex, currentContentIndex);
        }
    }

    // if (currentContentIndex < currNode.gpt_response[currentLetterIndex].content.length - 1) {
    //     currentContentIndex++;
    //     updateDisplayedContent('content' + currentLetterIndex, currentContentIndex);
    // }
};

function showCurrAnswerNames(dc_id) {
    // Show the current uploaded answer names
    var dropdownContent = document.getElementById(dc_id);
    if (dropdownContent.style.display === 'block') {
        dropdownContent.style.display = 'none';
    } else {
        dropdownContent.style.display = 'block';
    }
}

// TODO: detect the parent div of this context key element
function showContextKeys(contextKey) {
    console.log("In showContextKeys ...")
    // Show the context keys in all context-input divs
    var context_input_fork = document.getElementById('context-input-fork');
    var context_input_breakdown = document.getElementById('context-input-breakdown');
    var context_input_ccd = document.getElementById('context-input-ccd');

    context_input_fork.value += contextKey + ',';
    context_input_breakdown.value += contextKey + ',';
    context_input_ccd.value += contextKey + ',';

    // Hide the dropdown content
    document.getElementById('dropdown-content-answerNames-fork').style.display = 'none';
    document.getElementById('dropdown-content-answerNames-breakdown').style.display = 'none';
    document.getElementById('dropdown-content-answerNames-ccd').style.display = 'none';
}

function showAnswerNameOnContext(answerName, has_answer_draft=false){
    if (has_answer_draft) {
        // Show the answer name on the context input
        document.getElementById('context-input').value += '$' + answerName + '-answer-draft' + '$';
        // document.getElementById('dropdown-content-answerNames').style.display = 'none';
    } else {
        // Show the answer name on the context input
        document.getElementById('context-input').value += '$' + answerName + '$';
    }
    document.getElementById('dropdown-content-answerNames').style.display = 'none';
}

function showAnswerNameOnContextInFork(answerName) {
    // Show the answer name on the context input
    document.getElementById('context-input-fork').value += '$' + answerName + '-answer-draft' + '$';
    document.getElementById('dropdown-content-answerNames-fork').style.display = 'none';
}

function showAnswerOnContext(answerName) {
    // Show the answer name on the context input
    document.getElementById('context-input').value += '$' + answerName + '-answer-draft' + '$';
    document.getElementById('dropdown-content-answerNames').style.display = 'none';
}

function showFileNameOnContext(fileid) {
    console.log("In showFileNameOnContext ...")

    document.getElementById('context-input').value += '$' + fileid + '$';
    document.getElementById('dropdown-content-answerNames').style.display = 'none';

}

function showContent(id) {
    console.log("In showContent")
    console.log(id)
    var contents = document.getElementsByClassName('content');
    for (var i = 0; i < contents.length; i++) {
        contents[i].style.display = 'none';
    }
    document.getElementById(id).style.display = 'block';

    // Update the current content div index
    currentLetterIndex = id.split('content')[1];

    // Reset content index to show the first content initially
    currentContentIndex = 0;
    updateDisplayedContent(id, currentContentIndex);
}

function createForkNodes(response, context_descriptions, duration) {
    console.log("In createForkNodes ...")
    // create forked nodes based on contexts
    // split response based on new line
    var nodes = response.split(/\n/);
    
    for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        var nodeStepId = i;
        var nodeText = currNode.text + ': ' + node;  // identify potential universities by 03/15/24
        var deadline = "";
        var description = currNode.description;
        if (context_descriptions[i] != '') {
            description = context_descriptions[i]
        }

        var new_level = currNode.level + 1;
        // var nodeId = `${new_level}-${currNode.step_id}-${nodeStepId}`;
        var nodeId = `${Object.keys(nodeMap).length}-${new_level}-${currNode.step_id}-${nodeStepId}`

        const newNode = new TreeNode(nodeId, nodeText, nodeStepId, new_level, currNode.id, desc=description, deadline=deadline, need_subtasks=false, duration=duration);
        currNode.addChild(newNode);
        addNodeToMap(newNode);
    }

    showChildren(currNode);
    checkProgress(currNode);
}

function createSteps(response_steps) {
    // create and show steps on tree
    var steps = response_steps.split(/\d+\.\s+/); // Split on the number, period, and space

    // Remove the first empty string if it's there because of split at the beginning of the text
    if (steps[0] === '') {
        steps.shift();
    }

    acceptSteps(steps);
}

function showActionResults(response, index, query, action) {
    console.log("In showActionResults ... ")
    // console.log(response)
    // var steps_result_box = document.getElementById('steps_output');
    var brainstorm_result_box = document.getElementById('brainstorm_output');
    // var draft_result_box = document.getElementById('draft_output');
    // steps_result_box.innerHTML = '';
    // brainstorm_result_box.innerHTML = '';
    // draft_result_box.innerHTML = '';
    if (action === 'steps') {  // steps
        var steps_header = document.createElement('h5');
        steps_header.innerHTML = "Steps";
        document.getElementById('steps').appendChild(steps_header);

        var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
        var length = steps.length;  // length of steps
        var formattedSteps = '';

        // Remove the first empty string if it's there because of split at the beginning of the text
        if (steps[0] === '') {
            steps.shift();
        }

        // Map each step to a list item
        var formattedSteps = steps.map(function(step) {
            // Find the index of the first semicolon
            var semicolonIndex = step.indexOf(':');
            if (semicolonIndex !== -1) {
                // Split the step into two parts and bold the first
                return '<li><strong>' + step.substring(0, semicolonIndex + 1) + '</strong>' + step.substring(semicolonIndex + 1) + '</li>';
            } else {
                // If there is no semicolon, return the step as is
                return '<li>' + step + '</li>';
            }
            // return '<li>' + step.trim() + '</li>'; // Trim each step and wrap it in <li> tags
        }).join(''); // Join all list items into a single string

        // // append a <h6> "Prompt" after the list of steps
        // var prompt = document.createElement('h6');
        // prompt.innerHTML = "Prompt";
        // steps_result_box.appendChild(prompt);

        // // add textarea to store the prompt query
        // var textarea = document.createElement("textarea");
        // textarea.value = query;
        // textarea.rows = 5;
        // textarea.id = 'result_action' + index + "_prompt" + 0;
        // steps_result_box.appendChild(textarea);

        // add a "regenerate" button under textarea
        // var regenerateButton = document.createElement("button");
        // regenerateButton.innerHTML = "Regenerate";
        // regenerateButton.id = 'button_regenerate' + index;
        // // regenerateButton.onclick = regenerate(index);
        // steps_result_box.appendChild(regenerateButton);
        // document.getElementById('button_regenerate' + index).addEventListener('click', function() {
        //     regenerate(index, action);
        // });

        // add a line break to seperate the accept button from the "prompt" h6 tag below 
        // steps_result_box.appendChild(document.createElement("br"));
        steps_result_box.appendChild(document.createElement("br"));
        
        // append the list of steps to the result_box
        var result = document.createElement('div');
        result.innerHTML = '<ul>' + formattedSteps + '</ul>';
        steps_result_box.appendChild(result);

        // result_box.innerHTML = '<ul>' + formattedSteps + '</ul>';
        // add a "Accept" button under the list of steps to expand the trees
        var acceptButton = document.createElement("button");
        acceptButton.innerHTML = "Accept";
        acceptButton.onclick = function() { acceptSteps(steps); };
        steps_result_box.appendChild(acceptButton);
    } 
    // else if (index == 1) {
    //     var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
    //     var length = steps.length;  // length of steps
    //     var formattedSteps = '';

    //     // Remove the first empty string if it's there because of split at the beginning of the text
    //     if (steps[0] === '') {
    //         steps.shift();
    //     }

    //     // Map each step to a list item
    //     var formattedSteps = steps.map(function(step) {
    //         // get step id from steps
    //         var stepid = steps.indexOf(step);
    //         return `
    //             <li class='result-input-container'>
    //                 <div class="column gpt-response" id="res-${inputCount}-${stepid}">
    //                     ${step.trim()}
    //                 </div>
    //                 <div class="column step-textarea">
    //                     <textarea type="text" id="cli-${inputCount}-${stepid}-textarea" placeholder="Type your input..." rows="3" cols="30"></textarea>
    //                 </div>
    //             </li>
    //         `

    //     }).join(''); // Join all list items into a single string

    //     // append a <h6> "Prompt" after the list of steps
    //     var prompt = document.createElement('h6');
    //     prompt.innerHTML = "Prompt";
    //     result_box.appendChild(prompt);

    //     // add textarea to store the prompt query
    //     var textarea = document.createElement("textarea");
    //     textarea.value = query;
    //     textarea.rows = 10;
    //     result_box.appendChild(textarea);

    //     // add a "regenerate" button under textarea
    //     var regenerateButton = document.createElement("button");
    //     regenerateButton.innerHTML = "Regenerate";
    //     regenerateButton.id = 'button_regenerate' + index;
    //     // regenerateButton.onclick = regenerate(index);
    //     result_box.appendChild(regenerateButton);
    //     document.getElementById('button_regenerate' + index).addEventListener('click', function() {
    //         regenerate(index);
    //     });

    //     // add a line break to seperate the accept button from the "prompt" h6 tag below 
    //     result_box.appendChild(document.createElement("br"));
    //     result_box.appendChild(document.createElement("br"));
        
    //     // contentDiv.html('<ul>' + formattedSteps + '</ul>');
    //     var result = document.createElement('div');
    //     result.innerHTML = '<ul>' + formattedSteps + '</ul>';
    //     result_box.appendChild(result);

    //     // add a textarea to store the synthesis query
    //     var textarea = document.createElement("textarea");
    //     textarea.id = 'synthesize_query';
    //     textarea.placeholder = "Type your query for synthesis here...";
    //     textarea.rows = 3;
    //     result_box.appendChild(textarea);   

    //     // add a "synthesis" button under "results-box" classs
    //     var synthesisButton = document.createElement("button");
    //     synthesisButton.innerHTML = "Synthesize";
    //     synthesisButton.id = 'synthesis_' + currNode.id;
    //     // synthesisButton.onclick = synthesis;
    //     result_box.appendChild(synthesisButton);
    //     document.getElementById('synthesis_' + currNode.id).addEventListener('click', function() {
    //         synthesis();
    //     });
    // } 
    else if (action == 'brainstorm') {

        var brainstorm_header = document.createElement('h5');
        brainstorm_header.innerHTML = "";
        document.getElementById('brainstorm').appendChild(brainstorm_header);
        // return response as a textarea element in 'result-box' and create navigation buttons for iterating
        var response_ = []
        response_.push(response);
        console.log(response_)
        currNode.gpt_response = response_;

            // create a new div of class "result-box" and id "brainstorm_output"
        var r_box = document.createElement('div');
        r_box.id = 'brainstorm_output';
        r_box.className = 'result-box';

        // var r_box = document.getElementById('output');
        response_.forEach(function(brainstorm_texts, idx) {
            // Create content div
            var c_Div = document.createElement('div');
            c_Div.id = 'content_brainstorm' + idx;
            c_Div.className = 'content_brainstorm';

            // Create textarea
            var textarea = document.createElement('textarea');
            textarea.id = 'content_brainstorm' + idx + "_textarea" + 0;
            textarea.value = brainstorm_texts;
            textarea.rows = 15;
            c_Div.appendChild(textarea);

            // Append elements to the container
            r_box.appendChild(c_Div);
        });
        brainstorm_result_box.appendChild(r_box);

        // create a navigation-panel div
        var nav_panel = document.createElement('div');
        nav_panel.id = 'navigation-panel';
        nav_panel.className = 'navigation-panel';
        nav_panel.innerHTML = `
                <button class="sd-button-small" id="prev" onclick="show_prev_draft()">&#8592;</button>
                <button class="sd-button-small" id="next" onclick="show_next_draft()">&#8594;</button>
                <textarea type="text" id="reg-query" placeholder="Specify details to get a new draft. E.g. 'Show me the schools in US only.' " rows="1" cols="100"></textarea>
                <button class="sd-button" id="regenerate" onclick="reg_draft(${index})">Show me an iterated version</button>
            `;
        brainstorm_result_box.appendChild(nav_panel);
    } 
    // else {  // write a draft

    //     var draft_header = document.createElement('h5');
    //     draft_header.innerHTML = "Write a draft";
    //     document.getElementById('draft').appendChild(draft_header);

    //     var textarea = document.createElement("textarea");
    //     var response_ = response.split("###").map(function(letter) {
    //         // ignore the first element based on id
    //         if (letter === '') {
    //             return;
    //         }
            
    //         var title = letter.split("\n")[0].trim();
    //         var dft = letter.split("\n").slice(1).join("\n").trim();
    //         var content = [];
    //         content.push(dft);

    //         return {title: title, content: content};
    //     });
    //     // delete the first element of the list if it's empty
    //     if (response_[0] === undefined) {
    //             response_.shift();
    //     }
    //     currNode.gpt_response = response_;  // a list of all responses
        
    //     // append a <h6> "Prompt" after the list of steps
    //     var prompt = document.createElement('h6');
    //     prompt.innerHTML = "Prompt";
    //     draft_result_box.appendChild(prompt);

    //     // add textarea to store the prompt query
    //     var textarea = document.createElement("textarea");
    //     textarea.value = query;
    //     textarea.rows = 10;
    //     textarea.id = 'result_action' + index + "_prompt" + 0;
    //     draft_result_box.appendChild(textarea);

    //     // add a "regenerate" button under textarea
    //     var regenerateButton = document.createElement("button");
    //     regenerateButton.innerHTML = "Regenerate";
    //     regenerateButton.id = 'button_regenerate' + index;
    //     // regenerateButton.onclick = regenerate(index);
    //     draft_result_box.appendChild(regenerateButton);
    //     document.getElementById('button_regenerate' + index).addEventListener('click', function() {
    //         regenerate(index);
    //     });

    //     // add a line break to seperate the accept button from the "prompt" h6 tag below 
    //     draft_result_box.appendChild(document.createElement("br"));
    //     draft_result_box.appendChild(document.createElement("br"));
        
    //     // create a new div of id 'radio-draft'
    //     var radio_draft = document.createElement('div');
    //     radio_draft.id = 'radio-draft';
    //     // create a new div of class "result-box" and id "draft_output"
    //     var draft_output = document.createElement('div');
    //     draft_output.id = 'draft_output';
    //     draft_output.className = 'result-box';
    //     response_.forEach(function(draft, index) {
    //         // check if the first element in draft.content is an empty string
    //         if (draft.content[0] !== '') {
    //             // Create radio button
    //             var radioButton_draft = document.createElement('input');
    //             radioButton_draft.type = 'radio';
    //             radioButton_draft.id = 'part' + index;
    //             radioButton_draft.name = 'outline';
    //             radioButton_draft.onclick = function() { showContent('content_draft' + index); };

    //             // Create label
    //             var label = document.createElement('label');
    //             label.htmlFor = 'part' + index;
    //             label.textContent = draft.title;

    //             // Create content div
    //             var c_div = document.createElement('div');
    //             c_div.id = 'content_draft' + index;
    //             c_div.className = 'content';

    //             // Iterate through each content string in the array and create a textarea for it
    //             draft.content.forEach(function(contentString, contentIndex) {
    //                 var textarea = document.createElement('textarea');
    //                 textarea.id = 'content_draft' + index + "_textarea" + contentIndex;
    //                 textarea.value = contentString;
    //                 textarea.rows = 5;
    //                 c_div.appendChild(textarea);
    //             });

    //             // Append elements to the container
    //             radio_draft.appendChild(radioButton_draft);
    //             radio_draft.appendChild(label);
    //             radio_draft.appendChild(document.createElement('br')); // Line break for better formatting
    //             draft_output.appendChild(c_div);
    //         }
    //     });
    //     draft_result_box.appendChild(radio_draft);
    //     draft_result_box.appendChild(draft_output);
    //     // By default, make the first radiobutton as clicked and show its contents
    //     radio_draft.firstChild.checked = true;
    //     // id of the first content div
    //     // firstContentDivId = 'content_draft' + radio_draft.firstChild.id.split('part')[1];
    //     // showContent(firstContentDivId);
    //     // create a navigation-panel div
    //     var nav_panel = document.createElement('div');
    //     nav_panel.id = 'navigation-panel-draft';
    //     nav_panel.className = 'navigation-panel';
    //     nav_panel.innerHTML = `
    //         <button id="prev" onclick="show_prev_draft()">&#8592; Prev</button>
    //         <button id="next" onclick="show_next_draft()">Next &#8594;</button>
    //         <textarea type="text" id="reg-query" placeholder="Type your specifications to iterate ..." rows="1" cols="100"></textarea>
    //         <button id="regenerate" onclick="reg_draft(${index})">Show me an iterated version</button>
    //     `;
    //     draft_result_box.appendChild(nav_panel);
    // }
}

function synthesis() {
    console.log("In synthesis")
    // iterate over all step-textareas and copy the textarea values to answer draft box
    var textareas = document.querySelectorAll('.step-textarea');
    var allTexts = '';

    // Iterate over each textarea and concatenate their values
    textareas.forEach(function(textarea) {
        var textarea_id = textarea.childNodes[1].id;
        var user_input = document.getElementById(textarea_id).value;

        if (user_input) {
            allTexts += user_input.trim() + "\n"; // Add a newline for separation
        }
    });

    // document.getElementById("answer-draft").value += allTexts.trim();
    console.log(`answerDraft ${document.getElementById("answer-draft").value}`)
    console.log(`allTexts ${allTexts.trim()}`)

    const purpose = $("#purpose").val();
    const query = $("#synthesize_query").val();
    const answer_draft = $("#answer-draft").val();
    const brainstorm_texts = allTexts.trim();
    const sub_goal = `${currNode.text}`;
    let data = {"query":query, "purpose":purpose, "answer_draft":answer_draft, "brainstorm_texts":brainstorm_texts, "sub_goal":sub_goal}
    console.log(data)
    $.ajax({
        type: "POST",
        url: "/synthesize",                
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(data),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("synthesis")
            console.log(data)
            // let prompt = data["prompt"]
            // document.getElementById("prompt-c").innerHTML = prompt;
            
            let response = data["response"]
            response = response.replace(/\n/g, "<br>");
            $("#output").html(response);
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        }
    })
}

function emptyAllContextInputs() {
    // empty all context inputs
    document.getElementById('context-input-fork').value = '';
    document.getElementById('context-input-breakdown').value = '';
    document.getElementById('context-input-ccd').value = '';
}

function emptyPrevResults() {
    if (currentOption == "steps") {
        if (currNode !== null) {
            if (currNode.children.length > 0) {
                currNode.children.forEach(child => {
                    removeNodeFromMap(child);
                });
                currNode.children = [];
            }
        }
    } else if (currentOption == "draft") {
        if (currNode !== null && currNode.option === "draft") {
            currNode.gpt_response = [];
            currNode.children.forEach(child => {
                removeNodeFromMap(child);
            });
            currNode.children = [];
        }
    }

    document.getElementById('brainstorm').innerHTML = '';
    document.getElementById('brainstorm_output').innerHTML = '';
    // document.getElementById('draft').innerHTML = '';
    // document.getElementById('draft_output').innerHTML = '';
}

function updateDropdownKey(key, value) {
    // update the dropdown content with the new key-value pair
    var dropdown_content_fork = document.getElementById('dropdown-content-answerNames-fork');
    // var dropdown_content_breakdown = document.getElementById('dropdown-content-answerNames-breakdown');
    // var dropdown_content_ccd = document.getElementById('dropdown-content-answerNames-ccd');

    var newDropDownitem = document.createElement('div');
    newDropDownitem.className = 'dropdown-content-items';
    newDropDownitem.innerHTML = `<a onclick="showContextKeys('` + `${key}` + `')" title="${value}">${key}</a>`;

    dropdown_content_fork.appendChild(newDropDownitem);
    // dropdown_content_breakdown.appendChild(newDropDownitem.cloneNode(true));
    // dropdown_content_ccd.appendChild(newDropDownitem.cloneNode(true));
}

function updateUserContext(node) {
    // update the global userContext and populate the changes to dropdown content

    const formGroup = document.getElementById('globalFormGroup-ced');
    const inputs = formGroup.querySelectorAll('input');

    // var newUserContext = {};

    // iterate over all input fields and store the values in newUserContext
    var customName = '';
    var customContent = '';
    inputs.forEach(input => {
        if (input.value !== '') {
            if (input.type === 'text') { // for text inputs
                if (input.id !== 'customName' && input.id !== 'customContent') {
                    // const label = formGroup.querySelector(`label[for="${input.id}"]`);
                    // const key = label ? label.textContent.trim() : input.name;
                    const key = input.id.split('context-input-ced-')[1];

                    user_context[key] = input.value;
                    node.curated_context_draft += key + ": " + input.value + "\n";

                    // populate the changes to dropdown content
                    updateDropdownKey(key, input.value);
                } else {
                    if (input.id === 'customName') {
                        customName = input.value;
                    } else if (input.id === 'customContent') {
                        customContent = input.value;
                    }

                    if (customName !== '' && customContent !== '') {
                        user_context[customName] = customContent;
                        node.curated_context_draft += customName + ": " + customContent + "\n";

                        // populate the changes to dropdown content
                        updateDropdownKey(customName, customContent);
                    }
                }
            
            } else { // file
                if (customName !== '') { // user upload new file
                    var label_key = customName;
                } else {
                    const input_id = "context-input-ced-" + input.id.split('File-ced')[0];
                    const label_file = formGroup.querySelector(`label[for="${input_id}"]`);
                    var label_key = label_file ? label_file.textContent.trim() : input.name;
                }

                // save the file to backend
                const file = input.files[0];
                let formData = new FormData();
                formData.append('file', file);
                let jsonData = {"label_key": label_key};
                formData.append('jsonData', JSON.stringify(jsonData));

                $.ajax({
                    type: "POST",
                    url: "/uploadUserContextFile",
                    data: formData,
                    processData: false,
                    contentType: false,
                    async: false,
                    beforeSend: function () { 
                        $("#spinner-div").show()
                    },
                    success: function(data) {
                        console.log("UserContextFile uploaded successfully");
                        fileContent = data["fileContent"];
                        
                        if (label_key in user_context) {
                            user_context[label_key] += fileContent;
                        } else {
                            user_context[label_key] = fileContent;
                        }

                        node.curated_context_draft += label_key + ": " + fileContent + "\n";

                        updateDropdownKey(label_key, fileContent);

                    },
                    error: function(request, status, error){
                        console.log("Error");
                        console.log(request)
                        console.log(status)
                        console.log(error)
                    }
                });
            }
        }
    });

    console.log("User Context after updating: ", user_context);
}

function output_all_results(responses, prompt_queries, actions) {
    console.log("output all results ... ")

    responses.forEach(function(response, index) {
        showActionResults(response.response, index, prompt_queries[index], actions[index]);
    });
}

function get_started_all(select_first_node=false) {
    console.log("get started all")
    // document.getElementById("taskSelection").classList.remove("hidden");
    // trigger an alert if currNode is not defined
    if (Object.keys(nodeMap).length === 1) { // assign currNode to root node
        currNode = nodeMap['level-0-1-0-0'];
    }

    if (currNode === null || currNode === undefined) {
        alert("Please select a goal from the tree");
        return;
    }

    console.log("Current Node: ", currNode);

    var curated_context_draft = '';
    if (currentOption !== 'steps') {
        emptyPrevResults();

        // take the contexts checked from checkboxList-ccd
        const checkboxList = document.getElementById('checkboxList-ccd');
        const checkedCheckboxes = checkboxList.querySelectorAll('input[type="checkbox"]:checked');
        let checkedLabels = [];
        checkedCheckboxes.forEach(checkbox => {
            const label = document.querySelector(`label[for="${checkbox.id}"]`).innerText;
            checkedLabels.push(label);
        });
        var curated_context_keys = checkedLabels.join(',');

        // check if 'context-inpu-ccd' contains any user provided keys
        if (document.getElementById('context-input-ccd').value !== '') {
            curated_context_keys += ',' + document.getElementById('context-input-ccd').value;
        }

        // take the contexts suggested in 'context-input-ccd'
        // var curated_context_keys = document.getElementById('context-input-ccd').value;
        console.log("Curated Context keys: ", curated_context_keys);
        curated_context_draft = printCuratedContexts(curated_context_keys);
        console.log("Curated Context Draft: ", curated_context_draft);
        currNode.curated_context_draft = curated_context_draft;
    }

    // get current tree structure in plain text
    let treeTexts = generateTreeString(nodeMap['level-0-1-0-0']);

    // get parent nodes of the current node
    let parentNodeTexts = generateParentString(currNode);

    // get the value of the textarea
    const purpose = document.getElementById('purpose').innerText;
    // const query = $("#query"+inputCount).val();
    const action = currentOption;
    // const sub_goal = `${currNode.text}`;
    const sub_goal = currNode.text + ` (${currNode.duration})`;
    const answer_draft = $("#answer-draft").val();
    // const prev_answer_draft = prevNodeAnswerDraft;
    const currTreeTexts = treeTexts;
    const currParentNodeTexts = parentNodeTexts;
    const deadline = `${currNode.deadline}`;
    const description = `${currNode.description}`;
    var context = printAllGlobalUserContexts();
    console.log("AllGlobalUserContext: ", context);
    
    if (currNode === nodeMap['level-0-1-0-0']) {
       // consider all user context for the root node decoomposition
       context += printAllLocalUserContexts();
    }
    
    if (curated_context_draft !== '') {
        context += curated_context_draft;
    }

    // construct system prompts
    let sys_prompt = '';
    sys_prompt += sys_prompt_user_purpose + '\n'
    
    // construct prompts for steps and brainstorm
    let prompt_steps = '';
    // let prompt_brainstorm = prompt_current_parent;
    // prompt_brainstorm += '\n' + document.getElementById('prompt').value;
    let prompt_brainstorm = document.getElementById('prompt').value;
    if (currNode.answer_draft.answer_draft_input !== '') {
        prompt_steps += prompt_steps_start + '\n\n' + prompt_user_current_answer + '\n\n' + prompt_current_structure + '\n\n' + prompt_suplemental_steps + '\n\n' + prompt_format_steps;
        
    } else if (currNode.answer_draft.answer_draft_input === '') {
        prompt_steps += prompt_steps_start + '\n\n' + prompt_current_structure + '\n\n' + prompt_suplemental_steps + '\n\n' + prompt_format_steps;

    }

    // let prompt_queries = [prompt_steps, prompt_brainstorm];
    if (action == 'steps') {
        var prompt_queries = [prompt_steps];
    } else {
        var prompt_queries = [prompt_brainstorm];
    }
    // let prompt_queries = [prompt_brainstorm];
    console.log(prompt_queries)
    

    // console.log(action)
    let jsonData = {
        "purpose":purpose, "sub_goal":sub_goal, "answer_draft":answer_draft, "curr_tree_texts": currTreeTexts, "curr_parents": parentNodeTexts, "deadline": deadline, "description": description, "prompt_queries": prompt_queries, "action": action, "filenames": filenames, "context": context, "sys_prompt": sys_prompt
    }
    console.log(jsonData)

    $.ajax({
        type: "POST",
        url: "/get_started_all",
        dataType : "json",
        contentType: "application/json; charset=utf-8",
        data : JSON.stringify(jsonData),
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("return from get started all")
            console.log(data)
            if (action == 'steps') {
                let response_steps = data["response_steps"]
                let responses = [
                    {title: "Suggested Subtasks", response: response_steps},
                ]
                console.log('responses-steps')
                console.log(responses)
                // append responses[0] to gpt_response_all
                currNode.gpt_response_steps = responses;  // a list of all responses
                if (accept_steps === true) {
                    // accept and create steps on the tree
                    createSteps(response_steps);
                    if (select_first_node) {
                        selectFirstNodeOfFirstLayer();
                    } else {
                        if (currNode.id === '0-1-0-0') {  // select root Node
                            selectRootNode();
                        }
                    }
                    // accept_steps = false;
                } else {
                    output_all_results(responses, prompt_queries, [action]);
                }
            } else {
                let response_brainstorm = data["response_brainstorm"]
                let responses = [
                    {title: "GPT Response", response: response_brainstorm},
                ]
                console.log('responses-brainstorm')
                console.log(responses)
                currNode.gpt_response_brainstorm = responses;  // a list of all responses
                output_all_results(responses, prompt_queries, [action]);
            }
            
            // empty checkboxList-ccd
            document.getElementById('checkboxList-ccd').innerHTML = '';
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        }
    })
}

function get_started() {

    // trigger an alert if currNode is not defined
    if (currNode === null || currNode === undefined) {
        alert("Please select a goal from the tree");
        return;
    }

    // empty the previous results when a new query is submitted
    emptyPrevResults();
    currNode.option = currentOption;
    
    // iterate over all step-textareas and copy the textarea values to answer draft box
    var textareas = document.querySelectorAll('.step-textarea');
    var allTexts = '';

    // Iterate over each textarea and concatenate their values
    textareas.forEach(function(textarea) {
        var textarea_id = textarea.childNodes[1].id;
        var user_input = document.getElementById(textarea_id).value;

        if (user_input) {
            allTexts += user_input.trim() + "\n"; // Add a newline for separation
        }
    });

    document.getElementById("answer-draft").value += allTexts.trim();
    console.log(`answerDraft ${document.getElementById("answer-draft").value}`)

    // check if there is a file to be uploaded
    let formData = new FormData();
    // var file = document.getElementById("fileUpload").files[0];
    var file = localStorage.getItem('uploadedFile');
    if (file) {
        formData.append('file', file);
    }

    // // check if prevNode contains answer draft
    // let prevNodeAnswerDraft = '';
    // let prevNodeSubGoal = '';
    // if (prevNode !== null && prevNode !== undefined) {
    //     prevNodeAnswerDraft = prevNode.answer_draft;
    //     prevNodeSubGoal = prevNode.text;
    // }

    // get current tree structure in plain text
    let treeTexts = generateTreeString(nodeMap['level-0-1-0-0']);

    // get the value of the textarea
    console.log("submit_query_button_"+inputCount)
    const purpose = document.getElementById('purpose').innerText;
    const query = $("#query"+inputCount).val();
    const action = currentOption;
    const sub_goal = `${currNode.text}`;
    const answer_draft = $("#answer-draft").val();
    // const prev_answer_draft = prevNodeAnswerDraft;
    const currTreeTexts = treeTexts;
    const deadline = `${currNode.deadline}`;
    const description = `${currNode.description}`;
    console.log(action) 
    let jsonData = {
        "query":query, "purpose":purpose, "action":action, "sub_goal":sub_goal, "answer_draft":answer_draft, "curr_tree_texts": currTreeTexts, "deadline": deadline, "description": description
    }
    console.log(jsonData)

    // Append JSON data as a string under a single key
    formData.append('jsonData', JSON.stringify(jsonData));

    $.ajax({
        type: "POST",
        url: "/get_started",
        processData: false,
        contentType: false,          
        // dataType : "json",
        // contentType: "application/json; charset=utf-8",
        data : formData,
        beforeSend: function () { 
            $("#spinner-div").show()
        },
        success: function(data, text){
            console.log("In get started ...")
            console.log(data)  

            let response = data["response"]
            if (action == "steps") {
                var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
                var length = steps.length;  // length of steps
                var formattedSteps = '';
                var tree_formattedSteps = '';

                // Remove the first empty string if it's there because of split at the beginning of the text
                if (steps[0] === '') {
                    steps.shift();
                }

                // iterate through the steps and create child nodes for current node
                for (var i = 0; i < steps.length; i++) {
                    var step = steps[i];
                    var stepid = i;
                    // take only the step texts before ':'
                    var stepText = step.split(":")[0];
                    var descriptions = step.split(":")[1];

                    var new_level = currNode.level + 1;
                    var nodeId = `${new_level}-${currNode.step_id}-${stepid}`;

                    const newNode = new TreeNode(nodeId, stepText, stepid, new_level, currNode.id, desc=descriptions);
                    currNode.addChild(newNode);
                    addNodeToMap(newNode);
                }
                
                // show the childs of the current node
                showChildren(currNode);
                checkProgress(currNode);

            } else if (action == 'framework_brainstorm') {
                var steps = response.split(/\d+\.\s+/); // Split on the number, period, and space
                var length = steps.length;  // length of steps
                var formattedSteps = '';
                var tree_formattedSteps = '';

                // Remove the first empty string if it's there because of split at the beginning of the text
                if (steps[0] === '') {
                    steps.shift();
                }
                
                var formattedSteps = steps.map(function(step) {
                    // get step id from steps
                    var stepid = steps.indexOf(step);
                    return `
                        <li class='result-input-container'>
                            <div class="column gpt-response" id="res-${inputCount}-${stepid}">
                                ${step.trim()}
                            </div>
                            <div class="column step-textarea">
                                <textarea type="text" id="cli-${inputCount}-${stepid}-textarea" placeholder="Type your input..." rows="3" cols="30"></textarea>
                            </div>
                        </li>
                    `

                }).join(''); // Join all list items into a single string


                $("#results-query"+inputCount).html('<ul>' + formattedSteps + '</ul>');

                // add a "synthesis" button under "results-box" classs
                var synthesisButton = document.createElement("button");
                synthesisButton.innerHTML = "Synthesize";
                synthesisButton.onclick = synthesis;
                document.getElementById("results-query"+inputCount).appendChild(synthesisButton);

            } else if (action == "draft") {
                // Take the "response" string. Output a list of dictionaries "letters" that contains the title and content for each letter based on "###" as the delimiter
                var response_ = response.split("###").map(function(letter) {
                    // ignore the first element based on id
                    if (letter === '') {
                        return;
                    }
                    
                    var title = letter.split("\n")[0].trim();
                    var dft = letter.split("\n").slice(1).join("\n").trim();
                    var content = [];
                    content.push(dft);

                    return {title: title, content: content};
                });

                // delete the first element of the list if it's empty
                if (response_[0] === undefined) {
                    response_.shift();
                }

                console.log(response_);
                currNode.gpt_response = response_;

                var radio_container = document.getElementById('radioContainer');
                var result_box = document.getElementById('results-query1');
                response_.forEach(function(draft, index) {
                    // check if the first element in draft.content is an empty string
                    if (draft.content[0] !== '') {
                        // Create radio button
                        var radioButton = document.createElement('input');
                        radioButton.type = 'radio';
                        radioButton.id = 'part' + index;
                        radioButton.name = 'outline';
                        radioButton.onclick = function() { showContent('content' + index); };

                        // Create label
                        var label = document.createElement('label');
                        label.htmlFor = 'part' + index;
                        label.textContent = draft.title;

                        // Create content div
                        var contentDiv = document.createElement('div');
                        contentDiv.id = 'content' + index;
                        contentDiv.className = 'content';

                        // Iterate through each content string in the array and create a textarea for it
                        draft.content.forEach(function(contentString, contentIndex) {
                            var textarea = document.createElement('textarea');
                            textarea.id = 'content' + index + "_textarea" + contentIndex;
                            textarea.value = contentString;
                            textarea.rows = 5;
                            contentDiv.appendChild(textarea);
                        });

                        // Append elements to the container
                        radio_container.appendChild(radioButton);
                        radio_container.appendChild(label);
                        radio_container.appendChild(document.createElement('br')); // Line break for better formatting
                        result_box.appendChild(contentDiv);
                    }
                });

                // By default, make the first radiobutton as clicked and show its contents
                radio_container.firstChild.checked = true;
                // id of the first content div
                firstContentDivId = 'content' + radio_container.firstChild.id.split('part')[1];
                showContent(firstContentDivId);

                // show the childs of the current node
                showChildren(currNode);
                $("#navigation-panel").html(`
                    <button class="sd-button-small" id="prev" onclick="show_prev_draft()">&#8592;</button>
                    <button class="sd-button-small" id="next" onclick="show_next_draft()">&#8594;</button>
                    <textarea type="text" id="reg-query" placeholder="Specify details to get a new draft. E.g. 'Show me the schools in US only.' " rows="1" cols="100"></textarea>
                    <button class="sd-button" id="regenerate" onclick="reg_draft(${index})">Show me an iterated version</button>
                `); 
            } else if (action === "brainstorm") {
                // return response as a textarea element in 'result-box' and create navigation buttons for iterating
                var response_ = []
                response_.push(response);
                console.log(response_);
                currNode.gpt_response = response_;  // a list of iterated responses

                var result_box = document.getElementById('results-query1');
                response_.forEach(function(brainstorm_texts, index) {
                    // Create content div
                    var contentDiv = document.createElement('div');
                    contentDiv.id = 'content' + index;
                    contentDiv.className = 'content';

                    // Create textarea
                    var textarea = document.createElement('textarea');
                    textarea.id = 'content' + index + "_textarea" + 0;
                    textarea.value = brainstorm_texts;
                    textarea.rows = 5;
                    contentDiv.appendChild(textarea);

                    // Append elements to the container
                    result_box.appendChild(contentDiv);
                });
                
                $("#navigation-panel").html(`
                    <button class="sd-button-small" id="prev" onclick="show_prev_draft()">&#8592;</button>
                    <button class="sd-button-small" id="next" onclick="show_next_draft()">&#8594;</button>
                    <textarea type="text" id="reg-query" placeholder="Specify details to get a new draft. E.g. 'Show me the schools in US only.' " rows="1" cols="100"></textarea>
                    <button class="sd-button" id="regenerate" onclick="reg_draft()">Show me an iterated version</button>
                `); 
            }
                
        },
        error: function(request, status, error){
            console.log("Error");
            console.log(request)
            console.log(status)
            console.log(error)
        },
        complete: function () { 
            $("#spinner-div").hide()
        }
    })
}

function highlightButton(buttonId) {
    // Remove the highlight from all buttons
    document.querySelectorAll('button').forEach(function(button) {
        button.classList.remove('highlighted');
    });

    // Highlight the clicked button
    document.getElementById(buttonId).classList.add('highlighted');
}

function toggleDropdown(draft_name) {
    var dropdown = document.getElementById(`dropdown-content-answerNames-${draft_name}`);
    if (dropdown.style.display === "none") {
        dropdown.style.display = "block";
    } else {
        dropdown.style.display = "none";
    }
}

function complete_answer_draft() {
    // complete draft and save files if any

    if (currNode === null || currNode === undefined) {
        alert("Please select a goal from the tree first.");
        return;
    }

    // click the checkbox for the completed goal/subgoal
    if (currNode !== null) {

        var draft_name = document.getElementById('draft-name').value;
        var answer_draft = document.getElementById('answer-draft').value;

        // add 'title' attribute to text-currNode.id element
        document.getElementById(`text-${currNode.id}`).setAttribute("title", draft_name);

        const file = document.getElementById('fileupload').files[0];
        // if (file) {
        //     document.getElementById('upload_filename').value = file.name;
        // }
        const file_id = document.getElementById('upload_filename').value;  // this is the user-specified id for the file
        const filedescription = document.getElementById('filedescription').value;


        if (answer_draft === '' && file_id === '') {
            alert("Please provide an answer draft or upload relevant files before completing the goal/subgoal.");
            return;
        }

        // update the current node
        currNode.is_completed = true;
        const checkbox = document.getElementById(`check-${currNode.id}`)
        checkbox.checked = true;
        currNode.answer_draft['answer_draft_input'] = answer_draft;

        const label = checkbox.nextElementSibling;
        label.classList.add('checked');

        // assumes there is only one file -> TODO: change this to handle multiple files
        if (file_id !== '') {
            currNode.answer_draft.files.push(
                {
                    "file_id": file_id,
                    "filedescription": filedescription
                }
            );
        }

        // display messages
        document.getElementById('feedbackMessage').style.display = 'block';
        document.getElementById('re-edit-btn').style.display = 'block';
        document.getElementById('answer-draft').disabled = true;
        document.getElementById('complete_answer').style.display = 'none';

        // update user_context
        user_context[draft_name] = answer_draft;
        
        let data = {"draft_name":draft_name, "answer_draft":answer_draft, "file_id": file_id, "filedescription": filedescription}
        console.log("In complete answer draft ...")
        console.log(data)

        var formData = new FormData();
        if (file) {
            formData.append('file', file);
        }
        formData.append('data', JSON.stringify(data));

        $.ajax({
            type: "POST",
            url: "/submit_draft_and_upload_files",
            processData: false,
            contentType: false,          
            data : formData,
            // dataType : "json",
            // contentType: "application/json; charset=utf-8",
            // data : JSON.stringify(data),
            beforeSend: function () { 
                $("#spinner-div").show()
            },
            success: function(data, text){
                console.log(data)
                answer_draft_message = data["answer_draft"];
                files_upload_message = data["files"];
                var has_answer_draft = false;
                
                // add <a onclick="showAnswerNameOnContext('${draft_name}')">${draft_name}</a> to "dropdown-content-answerNames" element
                if (answer_draft_message === "draft submission successful") {
                    has_answer_draft = true;
                    // create "Answer Draft" as a dropdown item
                    document.getElementById('dropdown-content-answerNames').innerHTML += `<div class="dropdown-content-items"><a onclick="showAnswerNameOnContext('${draft_name}')">${draft_name}</a> <i class="fa-solid fa-caret-down" onclick="toggleDropdown('${draft_name}')"></i>  <div id="dropdown-content-answerNames-${draft_name}" style="display:none;"><a onclick="showAnswerNameOnContext('${draft_name}', '${has_answer_draft}')">Answer Draft</a></div></div>`

                    // document.getElementById('dropdown-content-answerNames').innerHTML += `<a onclick="showAnswerNameOnContext('${draft_name}')">${draft_name}</a>`;
                    document.getElementById('dropdown-content-answerNames-fork').innerHTML += `<a onclick="showAnswerNameOnContextInFork('${draft_name}')">${draft_name}</a>`;

                    // append a file icon to the label of the current node
                    if (document.getElementById(`label-${currNode.id}`).innerHTML.includes("fa-file-text") === false) {
                        document.getElementById(`label-${currNode.id}`).innerHTML += `<i class="fa fa-file-text" id="fa-${currNode.id}" aria-hidden="true" onclick="showAnswerOnContext('${draft_name}')" title="Answer"></i>`;
                    }
                }

                if (files_upload_message === "file upload successful") {
                    if (document.getElementById(`label-${currNode.id}`).innerHTML.includes("fa-paperclip") === false) {
                        document.getElementById(`label-${currNode.id}`).innerHTML += `<i class="fas fa-paperclip" id="ifas-${currNode.id}" aria-hidden="true" onclick="showFileNameOnContext('${file_id}')" title="${file_id}"></i>`;
                    }
                    
                    if (has_answer_draft === true) {
                        document.getElementById(`dropdown-content-answerNames-${draft_name}`).innerHTML += `<a onclick="showFileNameOnContext('${file_id}')">${file_id}</a>`

                    } else {
                        document.getElementById('dropdown-content-answerNames').innerHTML += `<div class="dropdown-content-items"><a onclick="showAnswerNameOnContext('${draft_name}')">${draft_name}</a> <i class="fa-solid fa-caret-down" onclick="toggleDropdown('${draft_name}')"></i>  <div id="dropdown-content-answerNames-${draft_name}" style="display:none;"><a onclick="showFileNameOnContext('${file_id}')">${file_id}</a></div></div>`
                    }
                }
            },
            error: function(request, status, error){
                console.log("Error");
                console.log(request)
                console.log(status)
                console.log(error)
            },
            complete: function () { 
                $("#spinner-div").hide()
            }
        })
    }
}

function updateFilename() {
    const file = document.getElementById('fileupload').files[0];
    if (file) {
        document.getElementById('upload_filename').value = file.name;
    }
}

function upload_files() {
    if (currNode === null || currNode === undefined) {
        alert("Please select a goal from the tree first.");
        return;
    }

    if (currNode !== null) {
        const file = document.getElementById('fileupload').files[0];
        // if (file) {
        //     document.getElementById('upload_filename').value = file.name;
        // }
        const file_id = document.getElementById('upload_filename').value;  // this is the user-specified id for the file
        const filedescription = document.getElementById('filedescription').value;
        const sub_goal = `${currNode.text}`;

        // add "title" attribute to ifas-currNode.id element
        // document.getElementById(`ifas-${currNode.id}`).setAttribute("title", file_id);

        // add item {filename: filename, filedescription: filedescription, sub_goal: sub_goal} to currNode.uploadFiles
        currNode.uploadFiles[file_id] = filedescription;

        let data = {"file_id":file_id, "filedescription":filedescription, "sub_goal":sub_goal}
        console.log(data)
        var formData = new FormData();
        formData.append('file', file);
        formData.append('data', JSON.stringify(data));

        $.ajax({
            type: "POST",
            url: "/submit_file",
            processData: false,
            contentType: false,          
            data : formData,
            beforeSend: function () { 
                $("#spinner-div").show()
            },
            success: function(data, text){
                console.log("In upload files ...")
                console.log(data)  
                document.getElementById('feedbackMessage-upload').style.display = 'block';

                // add <i class="fas fa-paperclip" id="ifas-${this.id}" aria-hidden="true" onclick="showFileNameOnContext('${this.id}')"></i> to "label-currNode.id" element
                document.getElementById(`label-${currNode.id}`).innerHTML += `<i class="fas fa-paperclip" id="ifas-${currNode.id}" aria-hidden="true" onclick="showFileNameOnContext('${currNode.id}')" title="${file_id}"></i>`;
            },
            error: function(request, status, error){
                console.log("Error");
                console.log(request)
                console.log(status)
                console.log(error)
            },
            complete: function () { 
                $("#spinner-div").hide()
            }
        })
    }
}

function re_edit() {
    // uncheck the checkbox for the completed goal/subgoal
    if (currNode !== null) {
        currNode.is_completed = false;
        const checkbox = document.getElementById(`check-${currNode.id}`)
        checkbox.checked = false;

        const label = checkbox.nextElementSibling;
        label.classList.remove('checked');

        document.getElementById('feedbackMessage').style.display = 'none';
        document.getElementById('re-edit-btn').style.display = 'none';
        document.getElementById('answer-draft').disabled = false;
        document.getElementById('complete_answer').style.display = 'block';
    }
}