class TreeNode {
    constructor(id, text, step_id=0, level=1, parentNodeID='', desc='', deadline='', need_subtasks=true, duration='', emotion_support='', gpt_response_steps=[], gpt_response_brainstorm = [], gpt_response=[], children=[], option=null, answer_draft={"answer_draft_name": id + '-' + text,"answer_draft_input": "","files": []}, is_completed=false, n_tasks=1, n_completed_tasks=0, uploadFiles={}, curated_context_draft='') {
        this.id = id;
        this.text = text;
        this.step_id = step_id;
        this.level = level;
        this.parentNodeID = parentNodeID;
        this.description = desc;
        this.deadline = deadline;
        this.need_subtasks = need_subtasks;
        this.duration = duration;
        this.emotion_support = emotion_support;
        this.gpt_response_steps = gpt_response_steps;
        this.gpt_response_brainstorm = gpt_response_brainstorm;
        this.gpt_response = gpt_response;
        this.children = children;
        this.option = option;
        // this.answer_draft_name = id + ' ' + text;
        this.answer_draft = answer_draft;
        this.is_completed = is_completed;
        this.n_tasks = n_tasks;
        this.n_completed_tasks = n_completed_tasks;
        this.uploadFiles = uploadFiles;  // dictionary to store the uploaded files: key is the file name and value is the file content descriptions input by the user
        this.curated_context_draft = curated_context_draft;  // the context needed to generate the current draft
    
    }
    addChild(node) {
        this.children.push(node);
    }

    // Method to render the node and its children in HTML
    render() {
        // detect if the node is a completed node
        var class_strikethrough = this.is_completed ? "strikethrough checked" : "strikethrough";
        var attribute_checkbox = this.is_completed ? "checked" : "";

        if (this.id === '0-1-0-0') {  // if root node
            // var html = `
            //     <li class="tree-node" id="level-${this.id}" draggable="true" ondragstart="onDragStart(event)" ondragover="onDragOver(event)" ondrop="onDrop(event) ondragleave="onDragLeave(event)">
            //         <span class="sortable-handle">&#x2630;</span>
            //         <span id="arrow-${this.id}" onclick="toggleSubTasks('${this.id}')" class="toggle-arrow open">&#x3e;</span>
            //         <input type="checkbox" id="check-${this.id}" class="checkbox" ${attribute_checkbox}>
            //         <label" class="${class_strikethrough}">
            //             <span id="purpose" onclick="selectNode('${this.id}')">${this.deadline} ${this.text}</span>
            //         </label>
            //         <ul class="active" id="active-level-${this.id}">
            //         </ul>
            //     </li>
            // `
            var html = `
                <li class="tree-node" id="level-${this.id}">
                    <span id="arrow-${this.id}" class="toggle-arrow">&#x3e;</span>
                    <label" class="${class_strikethrough}">
                        <span id="purpose" onclick="selectNode('${this.id}')">${this.text}</span>
                    </label>
                    <ul class="active" id="active-level-${this.id}">
                    </ul>
                </li>
            `
        } else {
            // this.hasCheckedChildren = this.children.some(child => child.is_completed);
            if (this.children.length > 0) {
                // var html = `
                //     <li class="tree-node" id="level-${this.id}" draggable="true" ondragstart="onDragStart(event)" ondragover="onDragOver(event)" ondrop="onDrop(event)"  ondragleave="onDragLeave(event)">
                //         <span class="sortable-handle">&#x2630;</span>
                //         <span id="arrow-${this.id}" onclick="toggleSubTasks('${this.id}')" class="toggle-arrow open">&#x3e;</span>
                //         <input type="checkbox" id="check-${this.id}" class="checkbox" ${attribute_checkbox}>
                //         <label" class="${class_strikethrough}">
                //             <span id="text-${this.id}" onclick="selectNode('${this.id}')">${this.deadline} ${this.text}${` (${this.n_completed_tasks}/${this.n_tasks} done)`}</span>
                //         </label>
                //         <ul class="active" id="active-level-${this.id}">
                //         </ul>
                //     </li>
                // `;
                var html = `
                    <li class="tree-node" id="level-${this.id}">
                        <span id="arrow-${this.id}" class="toggle-arrow">&#x3e;</span>
                        <input type="checkbox" id="check-${this.id}" class="checkbox" ${attribute_checkbox}>
                        <label" class="${class_strikethrough}">
                            <span id="text-${this.id}" onclick="selectNode('${this.id}')" title="${this.description}">${this.deadline} ${this.text} (${this.duration})</span>
                        </label>
                        <ul class="active" id="active-level-${this.id}">
                        </ul>
                    </li>
                `;
                
            } else {
                var has_answer_draft = false;
                if (this.answer_draft['answer_draft_input'] !== '' || this.answer_draft['files'].length > 0) { // has answer draft and uploaded files
                    // if (this.answer_draft['answer_draft_input'] !== '') { // has answer draft
                    has_answer_draft = true;
                    // if (this.answer_draft['answer_draft_input'] !== '' && this.answer_draft['files'].length === 0) {  // only contains answer draft
                    if (this.answer_draft['answer_draft_input'] !== '') {  // only contains answer draft
                        document.getElementById('dropdown-content-answerNames').innerHTML += `<div class="dropdown-content-items"><a onclick="showAnswerNameOnContext('${this.answer_draft['answer_draft_name']}')">${this.answer_draft['answer_draft_name']}</a> <i class="fa-solid fa-caret-down" onclick="toggleDropdown('${this.answer_draft['answer_draft_name']}')"></i>  <div id="dropdown-content-answerNames-${this.answer_draft['answer_draft_name']}" style="display:none;"><a onclick="showAnswerNameOnContext('${this.answer_draft['answer_draft_name']}', '${has_answer_draft}')">Answer Draft</a></div></div>`

                        // document.getElementById('dropdown-content-answerNames').innerHTML += `<a onclick="showAnswerNameOnContext('${draft_name}')">${draft_name}</a>`;
                        document.getElementById('dropdown-content-answerNames-fork').innerHTML += `<a onclick="showAnswerNameOnContextInFork('${this.answer_draft['answer_draft_name']}')">${this.answer_draft['answer_draft_name']}</a>`;

                        if (this.answer_draft['files'].length > 0) {
                             document.getElementById(`dropdown-content-answerNames-${this.answer_draft['answer_draft_name']}`).innerHTML += `<a onclick="showFileNameOnContext('${this.answer_draft['files'][0]['file_id']}')">${this.answer_draft['files'][0]['file_id']}</a>`
                        }
                    }
                    if (this.answer_draft['files'].length > 0) { // has uploaded files
                        document.getElementById('dropdown-content-answerNames').innerHTML += `<div class="dropdown-content-items"><a onclick="showAnswerNameOnContext('${this.answer_draft['answer_draft_name']}')">${this.answer_draft['answer_draft_name']}</a> <i class="fa-solid fa-caret-down" onclick="toggleDropdown('${this.answer_draft['answer_draft_name']}')"></i>  <div id="dropdown-content-answerNames-${this.answer_draft['answer_draft_name']}" style="display:none;"><a onclick="showFileNameOnContext('${this.answer_draft['files'][0]['file_id']}')">${this.answer_draft['files'][0]['file_id']}</a></div></div>`
                    }

                    // var html = `<li class="tree-node" id="level-${this.id}" draggable="true" ondragstart="onDragStart(event)" ondragover="onDragOver(event)" ondrop="onDrop(event)"  ondragleave="onDragLeave(event)">
                    //     <span class="sortable-handle">&#x2630;</span>
                    //     <span id="arrow-${this.id}" onclick="toggleSubTasks('${this.id}')" class="toggle-arrow">&#x3e;</span>
                    //     <input type="checkbox" id="check-${this.id}" class="checkbox" ${attribute_checkbox}>
                    //     <label class="${class_strikethrough}" class="node-label" id="label-${this.id}">
                    //         <span id="text-${this.id}" onclick="selectNode('${this.id}')">${this.deadline} ${this.text}</span>
                    //         <a class="dropbtn" onclick="showDropDownMenu('${this.id}')">&#9660;</a>
                    //         <div class="dropdown-content" id="dropdown-content-${this.id}">
                    //             <a onclick="expandSteps('${this.id}')">Breakdown</button>
                    //             <a onclick="removeNodeFromTree('${this.id}')">Remove</a>
                    //         </div>
                    //     </label>
                    //     <ul class="active" id="active-level-${this.id}">
                    //     </ul>
                    // </li>`;
                    var html = `<li class="tree-node" id="level-${this.id}">
                        <span id="arrow-${this.id}" class="toggle-arrow">&#x3e;</span>
                        <input type="checkbox" id="check-${this.id}" class="checkbox" ${attribute_checkbox}>
                        <label class="${class_strikethrough}" class="node-label" id="label-${this.id}">
                            <span id="text-${this.id}" onclick="selectNode('${this.id}')" title="${this.description}">${this.deadline} ${this.text} (${this.duration})</span>
                            <i class="fas fa-ellipsis-v" style="margin-left: 5px;color: #369" onclick="showDropDownMenu('${this.id}')"></i>
                            <div class="dropdown-content" id="dropdown-content-${this.id}">
                                <a onclick="expandSteps('${this.id}')">Breakdown</a>
                                <a onclick="removeNodeFromTree('${this.id}')">Remove</a>
                            </div>
                        </label>
                        <ul class="active" id="active-level-${this.id}">
                        </ul>
                    </li>`;
                }
                else {
                    // var html = `
                    //     <li class="tree-node" id="level-${this.id}" draggable="true" ondragstart="onDragStart(event)" ondragover="onDragOver(event)" ondrop="onDrop(event)"  ondragleave="onDragLeave(event)">
                    //         <span class="sortable-handle">&#x2630;</span>
                    //         <span id="arrow-${this.id}" onclick="toggleSubTasks('${this.id}')" class="toggle-arrow">&#x3e;</span>
                    //         <input type="checkbox" id="check-${this.id}" class="checkbox" ${attribute_checkbox}>
                    //         <label class="${class_strikethrough}" class="node-label" id="label-${this.id}">
                    //             <span id="text-${this.id}" onclick="selectNode('${this.id}')">${this.deadline} ${this.text}</span>
                    //             <a class="dropbtn" onclick="showDropDownMenu('${this.id}')">&#9660;</a>
                    //             <div class="dropdown-content" id="dropdown-content-${this.id}">
                    //                 <a onclick="expandSteps('${this.id}')">Breakdown</button>
                    //                 <a onclick="removeNodeFromTree('${this.id}')">Remove</a>
                    //             </div>
                    //         </label>
                    //         <ul class="active" id="active-level-${this.id}">
                    //         </ul>
                    //     </li>
                    // `;
                    var html = `
                        <li class="tree-node" id="level-${this.id}">
                            <span id="arrow-${this.id}" class="toggle-arrow">&#x3e;</span>
                            <input type="checkbox" id="check-${this.id}" class="checkbox" ${attribute_checkbox}>
                            <label class="${class_strikethrough}" class="node-label" id="label-${this.id}">
                                <span id="text-${this.id}" onclick="selectNode('${this.id}')" title="${this.description}">${this.deadline} ${this.text} (${this.duration})</span>
                                <i class="fas fa-ellipsis-v" style="margin-left: 5px;color: #369" onclick="showDropDownMenu('${this.id}')"></i>
                                <div class="dropdown-content" id="dropdown-content-${this.id}">
                                    <a onclick="expandSteps('${this.id}')">Breakdown</a>
                                    <a onclick="removeNodeFromTree('${this.id}')">Remove</a>
                                </div>
                            </label>
                            <ul class="active" id="active-level-${this.id}">
                            </ul>
                        </li>
                    `;
                }
            }
        }
        
        return html;
    }
}

const nodeMap = {};
let currNode = null; // current node being selected
let prevNode = null;  // previous node being selected
let draggedElement = null; // current node being dragged

// const forkstrings = ["to each", "in each", "for each", "of each", "on each"];

function addNodeToMap(node) {
    nodeid = 'level-' + node.id;
    nodeMap[nodeid] = node;
}

// add the node as well as its children to the map
function addNodeToMap_recursive(node) {
    addNodeToMap(node);
    node.children.forEach(child => {
        // create a child node
        const childNode = new TreeNode(child.id, child.text, child.step_id, child.level, child.parentNodeID, child.description, child.deadline, child.need_subtasks, child.emotion_support, child.gpt_response_steps, child.gpt_response_brainstorm, child.gpt_response, child.children, child.option, child.answer_draft, child.is_completed, child.n_tasks, child.n_completed_tasks, child.uploadFiles);
        addNodeToMap_recursive(childNode);
    });
}

function removeNodeFromMap(node) {
    nodeid = 'level-' + node.id;
    delete nodeMap[nodeid];
}

function removeNodeFromTree(nodeid) {
    console.log(`Remove node ${nodeid} from the tree`);
    const node = nodeMap['level-'+nodeid];
    console.log(node.text);
    removeNodeFromMap(node);
    // remove the node from the tree
    document.getElementById(`level-${nodeid}`).remove();

    // delete node from the parent node
    const parent_node = nodeMap['level-'+node.parentNodeID];
    parent_node.children = parent_node.children.filter(child => child.id !== node.id);
}

function showDropDownMenu(nodeid) {
    var dropdownContent = document.getElementById(`dropdown-content-${nodeid}`);
    if (dropdownContent.style.display === "block") {
        dropdownContent.style.display = "none";
    } else {
        dropdownContent.style.display = "block";
    }
}

function expandSteps(nodeid) {
    console.log(`expand button is clicked for node ${nodeid}`);
    const node = nodeMap['level-'+nodeid];
    console.log(node.text);
    currNode = node;

    document.getElementById(`dropdown-content-${nodeid}`).style.display = 'none';

    // check if userContext is an empty Object: if empty, nothing to curate
    if (Object.keys(user_context).length !== 0) {
        let data = {
            "main_purpose": taskInput,
            "task_name": node.text,
            "description": node.description,
            "user_context": user_context
        }
        $.ajax({
            type: "POST",
            url: "/fork_detection",
            dataType: "json",
            contentType: "application/json; charset=utf-8",
            data: JSON.stringify(data),
            contentType: 'application/json',
            beforeSend: function () { 
                $("#spinner-div").show()
            },
            success: function(data, text) {
                console.log(data);
                answer = data['answer'];
                if (answer == 'Yes') {
                    console.log('This is a fork node ...');
                    curated_context = data['context_curation']
                    console.log('Suggested context is: ' + curated_context);
                    // curated_context is a list with one element, delete the single quote in the it
                    if (curated_context.length === 1) {
                        curated_context = curated_context[0].replace(/'/g, '');
                        // input the suggested context to the textarea with id "context-input-fork"
                        document.getElementById('context-input-fork').value = '$' + curated_context + '-answer-draft$';
                    }
                    
                    modal.style.display = "block"; 
                } else {
                    console.log('This is a normal breakdown node ... ');
                    get_steps()
                    // context_curation_breakdown(node.text, node.description);
                }
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
        // }
    } else {  // nothing to curate -> directly breakdown
        get_steps();
    }

    
}

function toggleSubTasks(node_id) {
    var subtasks_id = 'active-level-' + node_id;
    var arrow_id = 'arrow-' + node_id;
    var subTasks = document.getElementById(subtasks_id);
    var arrow = document.getElementById(arrow_id);    
    console.log('In toggleSubTasks')
    console.log(subtasks_id)
    console.log(subTasks)
    console.log(arrow)

    if (subTasks.style.display === "none") {
      subTasks.style.display = "block";
      arrow.classList.add("open");
    } else {
      subTasks.style.display = "none";
      arrow.classList.remove("open");
    }
}

function attachExpandBtnListeners() {
    const expandBtns = document.querySelectorAll('.expand-btn');
    console.log(document.querySelectorAll('.expand-btn'))

    expandBtns.forEach(function(expandBtn) {
        expandBtn.addEventListener('click', function() {
            const nodeid = this.id.slice(11);
            console.log(`expand button is clicked for node ${nodeid}`);
            const node = nodeMap['level-'+nodeid];
            console.log(node.text);
            currNode = node;
            get_steps();
            // showChildren(node);
        });
    });

}

// function attachDropdownTreeListeners() {
//     var dropdowns = document.getElementsByClassName("dropbtn");
//     for (var i = 0; i < dropdowns.length; i++) {
//         dropdowns[i].addEventListener("click", function() {
//             var dropdownContent = this.nextElementSibling;
//             if (dropdownContent.style.display === "block") {
//                 dropdownContent.style.display = "none";
//             } else {
//                 dropdownContent.style.display = "block";
//             }
//         });
//     }
// }

function attachCheckboxListeners() {
    const checkboxes = document.querySelectorAll('.checkbox');
    console.log(document.querySelectorAll('.checkbox'))

    checkboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            const label = this.nextElementSibling;
            // get the id of the span element inside label (from index 1 to the end of the string)
            nodeid = label.children[0].id.slice(5);
            node = nodeMap['level-'+nodeid];

            if (this.checked) {
                label.classList.add('checked');
                node.is_completed = true;
                document.getElementById('feedbackMessage').style.display = 'block';
                document.getElementById('re-edit-btn').style.display = 'block';
                document.getElementById('answer-draft').disabled = true;
                document.getElementById('draft-name').disabled = true;
                document.getElementById('complete_answer').style.display = 'none';
                complete_answer_draft();   
            } else {
                label.classList.remove('checked');
                node.is_completed = false;
                document.getElementById('feedbackMessage').style.display = 'none';
                document.getElementById('re-edit-btn').style.display = 'none';
                document.getElementById('answer-draft').disabled = false;
                document.getElementById('draft-name').disabled = false;
                document.getElementById('complete_answer').style.display = 'block';
            }

            // checkProgress(node);
            // showProgress(node);
        });
    });
}

// Function to generate the tree structure as a string with proper indentation
function generateTreeString(node, depth = 0) {
    let indent = ' '.repeat(depth * 4); // Adjust indentation here
    let str = `${indent}${node.text}\n`;
    node.children.forEach(child => {
        str += generateTreeString(child, depth + 1);
    });
    return str;
}

// starting from the root node, generate the parent nodes down to the current node as a string
function generateParentString(node) {
    let str = `${node.text}`;
    if (node.parentNodeID !== '') {
        const parent_node = nodeMap['level-'+node.parentNodeID];
        str = generateParentString(parent_node) + ' -> ' + str;
    }
    return str;
}

function showChildren(node) {
    if (node.children.length === 0 && node.id === '0-1-0-0') {  // if root node
        document.getElementById(`treeContainer-ul`).innerHTML = node.render();
        attachCheckboxListeners();
        // attachDropdownTreeListeners();
        // attachExpandBtnListeners();
        return;
    } 
    if (node.children.length > 0) {
        // show the childs of the current node
        document.getElementById(`active-level-${node.id}`).innerHTML = '';
        node.children.forEach(child => {
            // check if child is of type TreeNode
            if (!(child instanceof TreeNode)) {
                child = nodeMap['level-'+child.id];
            }
            document.getElementById(`active-level-${node.id}`).innerHTML = document.getElementById(`active-level-${node.id}`).innerHTML + child.render();
        });
        // Attach click listeners
        attachCheckboxListeners();
        // attachDropdownTreeListeners();
        // attachExpandBtnListeners();
    }
}

function loadChildren(rootNode) {
    // show the root node
    document.getElementById(`treeContainer-ul`).innerHTML = rootNode.render();
    // show the children of the root node
    document.getElementById(`active-level-${rootNode.id}`).innerHTML = '';
    // recursively load children of the root node, including children of childrens
    rootNode.children.forEach(child => {
        // console.log(child);
        child_node = nodeMap['level-'+child.id];
        if (child_node.children.length == 0) {
            document.getElementById(`active-level-${rootNode.id}`).innerHTML = document.getElementById(`active-level-${rootNode.id}`).innerHTML + child_node.render();
        } else {
            document.getElementById(`active-level-${rootNode.id}`).innerHTML = document.getElementById(`active-level-${rootNode.id}`).innerHTML + child_node.render();
            showChildren(child_node);
        }
    });
    // Attach click listeners
    attachCheckboxListeners();
}

function checkProgress(node) {
    // iterate through the children of currNode and count the number of node that is completed
    if (node.children.length == 0) {
        node.n_tasks = 1;
        if (node.is_completed) {
            node.n_completed_tasks = 1;
        } else {
            node.n_completed_tasks = 0;
        }
    } else {
        if (node.n_tasks > node.n_completed_tasks) {
            node.n_tasks = node.children.length;
            node.children.forEach(child => {
                if (child.is_completed) {
                    node.n_completed_tasks += 1;
                }
            });
        }
    }
    showProgress(node);
}

function showProgress(node){
    // progress = '<h8>' + '<b>' + 'Progress: ' + '</b>' + node.n_completed_tasks + '/' + node.n_tasks + ' completed' + '</h8>';
    // $("#progress").html(progress);
    // change the span text based on id="text-${this.id}"
    var spanid = ''
    if (node.id === '0-1-0-0') {
        spanid = 'purpose';
    } else {
        spanid = 'text-' + node.id;
    }
    // let spanid = 'text-' + node.id;
    let element = document.getElementById(spanid);
    element.innerHTML = node.deadline + ' ' + node.text;
    // if (node.children.length > 0) {
    //     element.innerHTML = node.deadline + ' ' + node.text + ` (${node.n_completed_tasks}/${node.n_tasks} done)`;
    // } else {
    //     element.innerHTML = node.deadline + ' ' + node.text;
    // }
    // element.innerHTML = node.text + ` (${node.n_completed_tasks}/${node.n_tasks} done)`;
}

function updateAndShowCurrNode(nodeid) {
    // update currNode
    console.log(`Node ${nodeid} clicked and set to be the current node`);
    currNode = nodeMap['level-'+nodeid];
    console.log(currNode.text);

    // show the draft and uploaded files of currNode if exists
    if (currNode.answer_draft['answer_draft_input'] !== '') {
        if (document.getElementById(`label-${currNode.id}`).innerHTML.includes('<i class="fa fa-file-text"' === false)) {
            document.getElementById(`label-${currNode.id}`).innerHTML += `<i class="fa fa-file-text" id="fa-${currNode.id}" aria-hidden="true" onclick="showAnswerOnContext('${currNode.answer_draft['answer_draft_name']}')" title="Answer"></i>`;
        }
    }
    if (currNode.answer_draft['files'].length > 0) {
        if (document.getElementById(`label-${currNode.id}`).innerHTML.includes('<i class="fas fa-paperclip"' === false)) {
            document.getElementById(`label-${currNode.id}`).innerHTML += `<i class="fas fa-paperclip" id="ifas-${currNode.id}" aria-hidden="true" onclick="showFileNameOnContext('${currNode.answer_draft['files'][0]['file_id']}')" title="${currNode.answer_draft['files'][0]['file_id']}"></i>`;
        }
    }

    // close the context window
    var context_window = document.getElementById('context-window');
    context_window.style.display = 'none';

    // close the subtask window
    var subtask_window = document.getElementById('subtask-detection-container');
    subtask_window.style.display = 'none';

    // show the subtask-detection window if the current node needs subtasks
    if (currNode.need_subtasks === true) {
        var subtask_window = document.getElementById('subtask-detection-container');
        if (currNode.id === '0-1-0-0') {
            subtask_window.style.display = 'none';
        } else {
            subtask_window.style.display = 'block';
        }
    } else {
        context_window.style.display = 'block';
        var context_input_textarea = document.getElementById('context-input');
        context_input_textarea.value = printGlobalUserContextKeys();
    }

    // display the answer_draft of currNode
    const answer_draft = document.getElementById('answer-draft');
    answer_draft.value = currNode.answer_draft.answer_draft_input;

    const answer_draft_name = document.getElementById('draft-name');
    answer_draft_name.value = currNode.answer_draft.answer_draft_name;

    // display the uploaded files of currNode
    const file_id = document.getElementById('upload_filename');
    const file_desc = document.getElementById('filedescription');
    file_id.value = '';
    file_desc.value = '';
    if (currNode.answer_draft.files.length > 0) {
        console.log("Contain more than one files ... ")
        // file_id.value = Object.keys(currNode.uploadFiles)[0];
        // file_desc.value = currNode.uploadFiles[file_id.value];
        // document.getElementById('feedbackMessage-upload').style.display = 'block';
    } else {
        // document.getElementById('feedbackMessage-upload').style.display = 'none';
        console.log("No files uploaded ... ")
        var fileInput = document.getElementById('fileupload');
        fileInput.value = "";  // This will clear the selected files
    }

    // check progress of the node
    // checkProgress(currNode);
    // showProgress(currNode);

    // display the descriptions of currNode
    // const descriptions = document.getElementById('desc');
    if (currNode.id === '0-1-0-0') {
        $("#desc").html('<h4>' + '<b>' + 'Overview of Subtasks' + '</b>' + '</h4>' + currNode.description);
    } else {
        $("#desc").html('<h5>' + '<b>' + currNode.text + ` (${currNode.duration})` + '</b>' + '</h5>' + '<h6>' + currNode.description + '</h6>');        
    }
    
    // descriptions.innerHTML = currNode.descriptions;
    console.log(currNode.description);

    // update completion status
    if (currNode.is_completed) {
        document.getElementById('feedbackMessage').style.display = 'block';
        document.getElementById('re-edit-btn').style.display = 'block';
        document.getElementById('answer-draft').disabled = true;
        document.getElementById('draft-name').disabled = true;
        // do not show the complete button
        document.getElementById('complete_answer').style.display = 'none';

    } else {
        document.getElementById('feedbackMessage').style.display = 'none';
        document.getElementById('re-edit-btn').style.display = 'none';
        document.getElementById('answer-draft').disabled = false;
        document.getElementById('draft-name').disabled = false;
        // show the complete button
        document.getElementById('complete_answer').style.display = 'block';
    }

    if (currNode.gpt_response_brainstorm.length > 0) {
        // Display regenerate button and hide start button
        var sb_container = document.getElementById("startButtonContainer");
        sb_container.style.display = 'none';
        var reg_container = document.getElementById("regenButtonContainer");
        reg_container.style.display = 'block';


        document.getElementById('brainstorm').innerHTML = '';
        document.getElementById('brainstorm_output').innerHTML = '';
        let prompt_brainstorm = '';
        prompt_brainstorm += prompt_user_need_help + `${currNode.text}: ${currNode.description}`;
        output_all_results(currNode.gpt_response_brainstorm, [prompt_brainstorm], ['brainstorm']);
    } else {
        // Display regenerate button and hide start button
        var sb_container = document.getElementById("startButtonContainer");
        sb_container.style.display = 'block';
        var reg_container = document.getElementById("regenButtonContainer");
        reg_container.style.display = 'none';
        document.getElementById('brainstorm').innerHTML = '';
        document.getElementById('brainstorm_output').innerHTML = '';
    }

    // update current prompt
    var curr_prompt = '';
    curr_prompt += prompt_user_need_help + `${currNode.text}: ${currNode.description}`;
    var prompt_textarea = document.getElementById('prompt');
    prompt_textarea.value = curr_prompt;

    // update the system prompt
    var sys_prompt = '';
    sys_prompt += sys_prompt_user_purpose_verbose + `${nodeMap['level-0-1-0-0'].text}`;

    showChildren(currNode);
}

function selectRootNode() {
    var nodeid = '0-1-0-0';
    let element = document.getElementById('purpose');
    element.style.backgroundColor = 'yellow';
    element.style.color = 'black';

    updateAndShowCurrNode(nodeid);
}

function selectFirstNodeOfFirstLayer() {
    var nodeid = '1-2-0-0';
    var spanid = "text-1-2-0-0";
    let element = document.getElementById(spanid);
    element.style.backgroundColor = 'yellow';
    element.style.color = 'black';

    updateAndShowCurrNode(nodeid);
}

function selectNode(nodeid) {
    // unhighlight the previous node
    if (currNode !== null) {
        let prevSpanid = '';
        if (currNode.id === '0-1-0-0') {
            prevSpanid = 'purpose';
        } else {
            prevSpanid = 'text-' + currNode.id;
        }

        let prevElement = document.getElementById(prevSpanid);
        if (prevElement !== null) {
            prevElement.style.backgroundColor = '';
            prevElement.style.color = '';

            // update the answer_draft
            const answer_draft = document.getElementById('answer-draft');
            currNode.answer_draft.answer_draft_input = answer_draft.value;

            const answer_draft_name = document.getElementById('draft-name').value;
            currNode.answer_draft.answer_draft_name= answer_draft_name;
        }
    }

    // hightligh text
    var spanid = ''
    if (nodeid === '0-1-0-0') {
        console.log(`Root node is clicked`);
        spanid = 'purpose';
    } else {
        spanid = 'text-' + nodeid;
    }

    let element = document.getElementById(spanid);
    if (element.style.backgroundColor === 'yellow') {
        element.style.backgroundColor = '';
        element.style.color = '';

        console.log(`Node ${nodeid} is unclicked`);
        currNode = null;
    } else {
        element.style.backgroundColor = 'yellow';
        element.style.color = 'black';

        updateAndShowCurrNode(nodeid);
    }
        // update currNode
    //     console.log(`Node ${nodeid} clicked and set to be the current node`);
    //     currNode = nodeMap['level-'+nodeid];
    //     console.log(currNode.text);

    //     // show the draft and uploaded files of currNode if exists
    //     if (currNode.answer_draft['answer_draft_input'] !== '') {
    //         if (document.getElementById(`label-${currNode.id}`).innerHTML.includes('<i class="fa fa-file-text"' === false)) {
    //             document.getElementById(`label-${currNode.id}`).innerHTML += `<i class="fa fa-file-text" id="fa-${currNode.id}" aria-hidden="true" onclick="showAnswerOnContext('${currNode.answer_draft['answer_draft_name']}')" title="Answer"></i>`;
    //         }
    //     }
    //     if (currNode.answer_draft['files'].length > 0) {
    //         if (document.getElementById(`label-${currNode.id}`).innerHTML.includes('<i class="fas fa-paperclip"' === false)) {
    //             document.getElementById(`label-${currNode.id}`).innerHTML += `<i class="fas fa-paperclip" id="ifas-${currNode.id}" aria-hidden="true" onclick="showFileNameOnContext('${currNode.answer_draft['files'][0]['file_id']}')" title="${currNode.answer_draft['files'][0]['file_id']}"></i>`;
    //         }
    //     }

    //     // close the context window
    //     var context_window = document.getElementById('context-window');
    //     context_window.style.display = 'none';

    //     // close the subtask window
    //     var subtask_window = document.getElementById('subtask-detection-container');
    //     subtask_window.style.display = 'none';

    //     // show the subtask-detection window if the current node needs subtasks
    //     if (currNode.need_subtasks === true) {
    //         var subtask_window = document.getElementById('subtask-detection-container');
    //         if (currNode.id === '0-1-0-0') {
    //             subtask_window.style.display = 'none';
    //         } else {
    //             subtask_window.style.display = 'block';
    //         }
    //     } else {
    //         context_window.style.display = 'block';
    //         var context_input_textarea = document.getElementById('context-input');
    //         context_input_textarea.value = printGlobalUserContextKeys();
    //     }


    //     // display the answer_draft of currNode
    //     const answer_draft = document.getElementById('answer-draft');
    //     answer_draft.value = currNode.answer_draft.answer_draft_input;

    //     const answer_draft_name = document.getElementById('draft-name');
    //     answer_draft_name.value = currNode.answer_draft.answer_draft_name;

    //     // display the uploaded files of currNode
    //     const file_id = document.getElementById('upload_filename');
    //     const file_desc = document.getElementById('filedescription');
    //     file_id.value = '';
    //     file_desc.value = '';
    //     if (currNode.answer_draft.files.length > 0) {
    //         console.log("Contain more than one files ... ")
    //         // file_id.value = Object.keys(currNode.uploadFiles)[0];
    //         // file_desc.value = currNode.uploadFiles[file_id.value];
    //         // document.getElementById('feedbackMessage-upload').style.display = 'block';
    //     } else {
    //         // document.getElementById('feedbackMessage-upload').style.display = 'none';
    //         console.log("No files uploaded ... ")
    //         var fileInput = document.getElementById('fileupload');
    //         fileInput.value = "";  // This will clear the selected files
    //     }

    //     // check progress of the node
    //     // checkProgress(currNode);
    //     // showProgress(currNode);

    //     // display the descriptions of currNode
    //     // const descriptions = document.getElementById('desc');
    //     $("#desc").html('<h5>' + '<b>' + currNode.text + '</b>' + '</h5>' + '<h6>' + currNode.description + '</h6>');
    //     // descriptions.innerHTML = currNode.descriptions;
    //     // console.log(currNode.description);

    //     // update completion status
    //     if (currNode.is_completed) {
    //         document.getElementById('feedbackMessage').style.display = 'block';
    //         document.getElementById('re-edit-btn').style.display = 'block';
    //         document.getElementById('answer-draft').disabled = true;
    //         document.getElementById('draft-name').disabled = true;
    //         // do not show the complete button
    //         document.getElementById('complete_answer').style.display = 'none';

    //     } else {
    //         document.getElementById('feedbackMessage').style.display = 'none';
    //         document.getElementById('re-edit-btn').style.display = 'none';
    //         document.getElementById('answer-draft').disabled = false;
    //         document.getElementById('draft-name').disabled = false;
    //         // show the complete button
    //         document.getElementById('complete_answer').style.display = 'block';
    //     }

    //     if (currNode.gpt_response_brainstorm.length > 0) {
    //         // Display regenerate button and hide start button
    //         var sb_container = document.getElementById("startButtonContainer");
    //         sb_container.style.display = 'none';
    //         var reg_container = document.getElementById("regenButtonContainer");
    //         reg_container.style.display = 'block';


    //         document.getElementById('brainstorm').innerHTML = '';
    //         document.getElementById('brainstorm_output').innerHTML = '';
    //         let prompt_brainstorm = '';
    //         prompt_brainstorm += prompt_user_need_help + `${currNode.text}: ${currNode.description}`;
    //         output_all_results(currNode.gpt_response_brainstorm, [prompt_brainstorm], ['brainstorm']);
    //     } else {
    //         // Display regenerate button and hide start button
    //         var sb_container = document.getElementById("startButtonContainer");
    //         sb_container.style.display = 'block';
    //         var reg_container = document.getElementById("regenButtonContainer");
    //         reg_container.style.display = 'none';
    //         document.getElementById('brainstorm').innerHTML = '';
    //         document.getElementById('brainstorm_output').innerHTML = '';
    //     }

    //     // update current prompt
    //     var curr_prompt = '';
    //     curr_prompt += prompt_user_need_help + `${currNode.text}: ${currNode.description}`;
    //     var prompt_textarea = document.getElementById('prompt');
    //     prompt_textarea.value = curr_prompt;

    //     // update the system prompt
    //     var sys_prompt = '';
    //     sys_prompt += sys_prompt_user_purpose_verbose + `${nodeMap['level-0-1-0-0'].text}`;

    //     showChildren(currNode);
    // }
}

function onDragStart(event) {
    draggedElement = event.target;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/html", draggedElement.innerHTML);
    draggedElement.classList.add("dragging");
}

function onDragOver(event) {
    if (event.preventDefault) {
        event.preventDefault(); // Necessary for allowing drop
    }
    event.dataTransfer.dropEffect = "move";

    if (event.target.classList.contains("tree-node")) {
        event.target.classList.add("drag-target");
    }

    return false;
}

function onDragLeave(event) {
    // Remove highlighting from the target node
    if (event.target.classList.contains("tree-node")) {
        event.target.classList.remove("drag-target");
    }
}

function onDrop(event) {
    if (event.stopPropagation) {
        event.stopPropagation(); // Stops the browser from redirecting.
    }

    // Don't do anything if dropping the same element
    if (draggedElement !== event.target && event.target.classList.contains("tree-node")) {
        let draggedNode = nodeMap[draggedElement.id]
        let targetNode = nodeMap[event.target.id]

        let draggedParentNode = nodeMap["level-"+draggedNode.parentNodeID];
        let targetParentNode = nodeMap["level-"+targetNode.parentNodeID];

        if (draggedParentNode === targetParentNode) {
            let draggedIndex = draggedParentNode.children.indexOf(draggedNode);
            let targetIndex = draggedParentNode.children.indexOf(targetNode);

            // Swap positions in the parent's children array
            [draggedParentNode.children[draggedIndex], draggedParentNode.children[targetIndex]] =
                [draggedParentNode.children[targetIndex], draggedParentNode.children[draggedIndex]];

            // Update the DOM to reflect the new order
            let parentElement = document.getElementById(`active-level-${draggedParentNode.id}`);
            let draggedElementHTML = parentElement.children[draggedIndex].outerHTML;
            let targetElementHTML = parentElement.children[targetIndex].outerHTML;

            parentElement.children[draggedIndex].outerHTML = targetElementHTML;
            parentElement.children[targetIndex].outerHTML = draggedElementHTML;

            const highlightedElement = document.querySelector('.drag-target');
            if (highlightedElement) {
                highlightedElement.classList.remove('drag-target');
            }

            // Reattach event listeners after swapping
            attachDragEventListeners();
        }
    }

    draggedElement.classList.remove("dragging");
    draggedElement = null;
    return false;
}

function attachDragEventListeners() {
    document.querySelectorAll(".tree-node").forEach(node => {
        node.removeEventListener("dragstart", onDragStart);
        node.removeEventListener("dragover", onDragOver);
        node.removeEventListener("drop", onDrop);
        node.removeEventListener("dragleave", onDragLeave);

        node.addEventListener("dragstart", onDragStart);
        node.addEventListener("dragover", onDragOver);
        node.addEventListener("drop", onDrop);
        node.addEventListener("dragleave", onDragLeave)
    });
}

function initTree() {
    const root = new TreeNode("0-1-0-0", taskInput, 0, 1, "", "", deadline=taskInput_deadline);

    addNodeToMap(root);
    showChildren(root);

    get_steps(select_first_node=false);
    attachDragEventListeners();
}

// function to load an exising tree with the root node
function loadTree(rootNode) {
    console.log(`Load the tree with root node ${rootNode.text}`);
    console.log(rootNode);
    const root = new TreeNode(rootNode.id, rootNode.text, rootNode.step_id, rootNode.level, rootNode.parentNodeID, rootNode.description, rootNode.deadline, rootNode.need_subtasks, rootNode.emotion_support, rootNode.gpt_response_steps, rootNode.gpt_response_brainstorm, rootNode.gpt_response, rootNode.children, rootNode.option, rootNode.answer_draft, rootNode.is_completed, rootNode.n_tasks, rootNode.n_completed_tasks, rootNode.uploadFiles);

    addNodeToMap_recursive(root);
    loadChildren(root);

    // get_steps();
    attachDragEventListeners();
}

// window.onload = initTree;