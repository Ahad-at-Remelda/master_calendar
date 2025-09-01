


# {% load static %}
# {% load socialaccount %}

# <!DOCTYPE html>
# <html lang="en">
# <head>
#     <meta charset="UTF-8">
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     <title>Sync Calendars - Master Calendar</title>
#     <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
#     <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
#     <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Source+Sans+Pro:wght@300;400;500;600&display=swap" rel="stylesheet">
#     <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">

#     <style>
#         :root {
#             --background: #ffffff; --foreground: #374151; --card: #f8fafc;
#             --card-foreground: #1f2937; --primary: #374151; --primary-foreground: #ffffff;
#             --secondary: #6366f1; --secondary-foreground: #ffffff; --accent: #6366f1;
#             --accent-foreground: #ffffff; --border: #e5e7eb; --sidebar: #f8fafc;
#             --sidebar-foreground: #374151; --sidebar-border: #e5e7eb; --radius: 0.5rem;
#             --google-blue: #4285f4; --google-blue-hover: #3367d6; --microsoft-blue: #0078d4;
#             --microsoft-blue-hover: #106ebe; --booking-orange: #f97316; --booking-orange-hover: #ea580c;
#         }
#         body { font-family: 'Source Sans Pro', sans-serif; background: var(--background); color: var(--foreground); line-height: 1.6; }
#         h1, h2, h3, h4, h5, h6 { font-family: 'Playfair Display', serif; font-weight: 600; }
#         .sidebar { background: var(--sidebar); border-right: 1px solid var(--sidebar-border); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); transition: all 0.3s ease-in-out; position: relative; z-index: 1000; overflow-x: hidden; overflow-y: auto; }
#         .sidebar.collapsed { width: 0; min-width: 0; opacity: 0; visibility: hidden; }
#         .sidebar-toggle { position: fixed; top: 20px; left: 20px; z-index: 1001; background: var(--primary); color: var(--primary-foreground); border: none; border-radius: var(--radius); padding: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); transition: all 0.3s ease; cursor: pointer; }
#         .sidebar-toggle:hover { background: var(--secondary); transform: scale(1.05); }
#         .sidebar-toggle.sidebar-open { top: 15px; left: 285px; }
#         .sidebar-close { position: absolute; top: 15px; right: 15px; background: none; border: none; color: var(--sidebar-foreground); font-size: 1.5rem; cursor: pointer; padding: 5px; border-radius: var(--radius); transition: background 0.2s ease; }
#         .sidebar-close:hover { background: var(--border); }
#         .sidebar h4 { color: var(--primary); font-weight: 700; margin-bottom: 1.5rem; }
#         .sidebar h5 { font-size: 0.875rem; font-weight: 600; text-transform: uppercase; color: var(--sidebar-foreground); margin-top: 1.5rem; margin-bottom: 0.75rem; letter-spacing: 0.05em; }
#         .list-group-item { border: none; padding: 0.75rem 1rem; border-radius: var(--radius); transition: all 0.2s ease; background: transparent; margin-bottom: 0.25rem; }
#         .list-group-item:hover { background: var(--border); transform: translateX(4px); }
#         .list-group-item.active { background: var(--accent); color: var(--accent-foreground); }
#         .page-wrapper { display: grid; grid-template-columns: 320px 1fr; height: 100vh; transition: grid-template-columns 0.3s ease; }
#         .page-wrapper.sidebar-collapsed { grid-template-columns: 0fr 1fr; }
#         .main-content { flex-grow: 1; overflow-y: auto; background: var(--background); padding: 2.5rem; min-width: 0; }
#         .btn-modern { border-radius: var(--radius); font-weight: 500; padding: 0.75rem 1.5rem; transition: all 0.2s ease; border: none; font-family: 'Source Sans Pro', sans-serif; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; }
#         .btn-modern:hover { transform: translateY(-1px); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); text-decoration: none; }
#         .btn-google { background: var(--google-blue); color: white; border: none; }
#         .btn-google:hover { background: var(--google-blue-hover); color: white; transform: translateY(-1px); box-shadow: 0 4px 6px -1px rgba(66, 133, 244, 0.3); }
#         .btn-microsoft { background: var(--microsoft-blue); color: white; border: none; }
#         .btn-microsoft:hover { background: var(--microsoft-blue-hover); color: white; transform: translateY(-1px); box-shadow: 0 4px 6px -1px rgba(0, 120, 212, 0.3); }
#         .btn-outline-modern { background: transparent; border: 2px solid var(--border); color: var(--foreground); }
#         .btn-outline-modern:hover { background: var(--border); color: var(--foreground); }
#         .btn-secondary-modern { background: var(--booking-orange); color: white; }
#         .btn-secondary-modern:hover { background: var(--booking-orange-hover); color: white; }
#         .list-group-item-action.active {
#             border-width: 2px; border-color: var(--accent);
#         }
#         @media (max-width: 768px) {
#             .page-wrapper { grid-template-columns: 1fr; }
#             .sidebar { position: fixed; top: 0; left: 0; height: 100vh; width: 320px; z-index: 1000; }
#             .sidebar.collapsed { transform: translateX(-100%); width: 320px; opacity: 1; visibility: visible; }
#             .main-content { padding: 1.5rem; }
#             .sidebar-toggle.sidebar-open { left: 20px; top: 20px; }
#         }
#     </style>
# </head>
# <body>
#     <button class="sidebar-toggle" id="sidebarToggle" title="Toggle Sidebar"><i class="bi bi-list"></i></button>

#     <div class="page-wrapper" id="pageWrapper">
#         <div class="sidebar" id="sidebar">
#             <div class="p-4">
#                 <div class="d-flex justify-content-between align-items-center">
#                     <h2>Lets <i class="fa-solid fa-clock"></i> Sync</h2>
#                     <button class="sidebar-close d-md-none" id="sidebarClose">&times;</button>
#                 </div>
#                 <div class="mb-3"><span class="text-muted">Logged in as:</span> <strong class="text-primary">{{ user.username }}</strong></div>
#                 <hr class="my-4">

#                 <h5>Navigation</h5>
#                 <div class="list-group list-group-flush mb-4">
#                     <a href="{% url 'home' %}" class="list-group-item list-group-item-action">
#                         <i class="bi bi-calendar3 me-2"></i> Main Calendar
#                     </a>
#                     <a href="{% url 'sync_calendars' %}" class="list-group-item list-group-item-action active">
#                         <i class="bi bi-arrow-repeat me-2"></i> Sync Calendars
#                     </a>
#                 </div>

#                 <h5>Connect New Account</h5>
#                 <div class="d-grid gap-2 mb-4"><a href="{% provider_login_url 'google' process='connect' %}" class="btn btn-modern btn-google"><i class="bi bi-google me-2"></i> Connect Google Account</a><a href="{% provider_login_url 'microsoft' process='connect' %}" class="btn btn-modern btn-microsoft"><i class="bi bi-microsoft me-2"></i> Connect Outlook Account</a></div>
#                 <h5>Booking & Sharing</h5>
#                 <div class="d-grid gap-2 mb-3"><a class="btn btn-modern btn-outline-modern" href="{% url 'user_settings' %}"><i class="bi bi-gear-fill me-2"></i> Booking Settings</a></div>
#                 <div class="d-grid gap-2"><a class="btn btn-modern btn-secondary-modern" href="{% url 'add_event' %}"><i class="bi bi-plus-circle-fill me-2"></i> Add Local Event</a><form action="{% url 'account_logout' %}" method="post" class="d-grid">{% csrf_token %}<button type="submit" class="btn btn-modern btn-outline-modern"><i class="bi bi-box-arrow-right me-2"></i> Logout</button></form></div>
#             </div>
#         </div>
        
#         <div class="main-content">
#             <div class="container-fluid py-4">
#                 <h1 class="mb-4">Sync Calendars</h1>
#                 <p class="text-muted">Select a source and a destination calendar to create a new sync relationship.</p>
                
#                 {% if messages %}
#                     {% for message in messages %}
#                         <div class="alert {% if message.tags %}alert-{{ message.tags }}{% else %}alert-info{% endif %} alert-dismissible fade show" role="alert">
#                             {{ message }}
#                             <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
#                         </div>
#                     {% endfor %}
#                 {% endif %}
#                 <hr>

#                 <!-- Display existing sync relationships -->
#                 <div class="mb-5">
#                     <h4>Active Syncs</h4>
#                     <div class="list-group">
#                         {% for sync in active_syncs %}
#                             <div class="list-group-item d-flex justify-content-between align-items-center p-3">
#                                 <div class="d-flex align-items-center">
#                                     <i class="bi bi-{{ sync.source_provider }} {% if sync.source_provider == 'google' %}text-success{% else %}text-primary{% endif %} fs-4 me-3"></i>
#                                     <div>
#                                         <strong>{{ sync.source_name }}</strong><br>
#                                         <small class="text-muted">{{ sync.source_email }}</small>
#                                     </div>
#                                 </div>
#                                 <div class="text-center">
#                                     <span class="badge bg-primary">{{ sync.sync_type_display }}</span>
#                                     <div><i class="bi bi-arrow-right fs-3"></i></div>
#                                 </div>
#                                 <div class="d-flex align-items-center">
#                                     <i class="bi bi-{{ sync.dest_provider }} {% if sync.dest_provider == 'google' %}text-success{% else %}text-primary{% endif %} fs-4 me-3"></i>
#                                     <div>
#                                         <strong>{{ sync.dest_name }}</strong><br>
#                                         <small class="text-muted">{{ sync.dest_email }}</small>
#                                     </div>
#                                 </div>
#                                 <div>
#                                     <form action="{% url 'delete_sync' sync.id %}" method="POST" onsubmit="return confirm('Are you sure you want to delete this sync? All synced events will be removed from the destination calendar.');">
#                                         {% csrf_token %}
#                                         <button type="submit" class="btn btn-sm btn-outline-danger">
#                                             <i class="bi bi-trash"></i> Delete
#                                         </button>
#                                     </form>
#                                 </div>
#                             </div>
#                         {% empty %}
#                             <p class="text-muted">You have no active syncs.</p>
#                         {% endfor %}
#                     </div>
#                 </div>

#                 <!-- Create a NEW sync -->
#                 <h4>Create a New Sync</h4>
#                 <form id="create-sync-form" method="POST" action="{% url 'create_sync' %}">
#                     {% csrf_token %}
#                     <div class="row mt-3">
#                         <!-- Source Column -->
#                         <div class="col-md-5">
#                             <h5>1. Select Source Calendar</h5>
#                             <div id="source-calendars-list" class="list-group">
#                                 {% for cal in all_calendars %}
#                                     <button type="button" class="list-group-item list-group-item-action" data-calendar-id="{{ cal.id }}">
#                                         <i class="bi bi-{{ cal.provider }} {% if cal.provider == 'google' %}text-success{% else %}text-primary{% endif %} me-2"></i>
#                                         <strong>{{ cal.name }}</strong> ({{ cal.display_email }})
#                                     </button>
#                                 {% empty %}
#                                     <p class="text-muted p-2">No calendars found. Please connect a Google or Outlook account.</p>
#                                 {% endfor %}
#                             </div>
#                             <input type="hidden" name="source_calendar_id" id="source_calendar_input">
#                         </div>

#                         <!-- Middle Column for Sync Type -->
#                         <div class="col-md-2 d-flex flex-column align-items-center justify-content-center">
#                             <div class="mb-3">
#                                 <label for="sync-type-select" class="form-label">Sync Type</label>
#                                 <select class="form-select" id="sync-type-select" name="sync_type">
#                                     <option value="full_details" selected>Full Details</option>
#                                     <option value="private">Private Appointment</option>
#                                 </select>
#                             </div>
#                             <button type="submit" id="create-sync-btn" class="btn btn-primary" disabled>
#                                 <i class="bi bi-arrow-right-circle"></i> Create Sync
#                             </button>
#                         </div>

#                         <!-- Destination Column -->
#                         <div class="col-md-5">
#                             <h5>2. Select Destination Calendar</h5>
#                             <div id="destination-calendars-list" class="list-group">
#                                 {% for cal in all_calendars %}
#                                     <button type="button" class="list-group-item list-group-item-action" data-calendar-id="{{ cal.id }}">
#                                         <i class="bi bi-{{ cal.provider }} {% if cal.provider == 'google' %}text-success{% else %}text-primary{% endif %} me-2"></i>
#                                         <strong>{{ cal.name }}</strong> ({{ cal.display_email }})
#                                     </button>
#                                 {% empty %}
#                                     <p class="text-muted p-2">No calendars found.</p>
#                                 {% endfor %}
#                             </div>
#                             <input type="hidden" name="destination_calendar_id" id="destination_calendar_input">
#                         </div>
#                     </div>
#                 </form>
#             </div>
#         </div>
#     </div>

#     <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
#     <script>
#     document.addEventListener('DOMContentLoaded', function () {
#         const sidebar = document.getElementById('sidebar');
#         const pageWrapper = document.getElementById('pageWrapper');
#         const sidebarToggle = document.getElementById('sidebarToggle');
#         const sidebarClose = document.getElementById('sidebarClose');

#         function toggleSidebar() {
#             sidebar.classList.toggle('collapsed');
#             pageWrapper.classList.toggle('sidebar-collapsed');
#             sidebarToggle.classList.toggle('sidebar-open');
#             const icon = sidebarToggle.querySelector('i');
#             icon.className = sidebar.classList.contains('collapsed') ? 'bi bi-list' : 'bi bi-x';
#         }

#         if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
#         if (sidebarClose) sidebarClose.addEventListener('click', toggleSidebar);
#         if (window.innerWidth <= 768) {
#             sidebar.classList.add('collapsed');
#             pageWrapper.classList.add('sidebar-collapsed');
#         }

#         const sourceList = document.getElementById('source-calendars-list');
#         const destinationList = document.getElementById('destination-calendars-list');
#         const sourceInput = document.getElementById('source_calendar_input');
#         const destinationInput = document.getElementById('destination_calendar_input');
#         const createSyncBtn = document.getElementById('create-sync-btn');

#         function checkFormState() {
#             const sourceSelected = sourceInput.value;
#             const destSelected = destinationInput.value;
#             createSyncBtn.disabled = !(sourceSelected && destSelected && sourceSelected !== destSelected);
#         }

#         sourceList.addEventListener('click', function(e) {
#             const button = e.target.closest('button.list-group-item-action');
#             if (!button) return;
            
#             sourceList.querySelectorAll('.active').forEach(btn => btn.classList.remove('active'));
#             button.classList.add('active');
#             sourceInput.value = button.dataset.calendarId;

#             destinationList.querySelectorAll('button').forEach(btn => {
#                 btn.style.display = (btn.dataset.calendarId === sourceInput.value) ? 'none' : 'block';
#             });
#             if (destinationInput.value === sourceInput.value) {
#                 destinationList.querySelectorAll('.active').forEach(btn => btn.classList.remove('active'));
#                 destinationInput.value = '';
#             }

#             checkFormState();
#         });

#         destinationList.addEventListener('click', function(e) {
#             const button = e.target.closest('button.list-group-item-action');
#             if (!button) return;

#             destinationList.querySelectorAll('.active').forEach(btn => btn.classList.remove('active'));
#             button.classList.add('active');
#             destinationInput.value = button.dataset.calendarId;

#             sourceList.querySelectorAll('button').forEach(btn => {
#                 btn.style.display = (btn.dataset.calendarId === destinationInput.value) ? 'none' : 'block';
#             });
#             if (sourceInput.value === destinationInput.value) {
#                 sourceList.querySelectorAll('.active').forEach(btn => btn.classList.remove('active'));
#                 sourceInput.value = '';
#             }

#             checkFormState();
#         });
#     });
#     </script>
# </body>
# </html> 