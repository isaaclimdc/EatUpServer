import os
from django.conf.urls import patterns, include, url
from django.conf import settings

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'eatupBackendProj.views.home', name='home'),
    # url(r'^eatupBackendProj/', include('eatupBackendProj.foo.urls')),
    url(r'^test$', 'eatupBackendApp.views.showIndex', name='index'),
    
    url(r'^info/user/', 'eatupBackendApp.views.getUser', name='get_user'),
    url(r'^info/event/', 'eatupBackendApp.views.getEvent', name='get_event'),
    url(r'^info/userevents/', 'eatupBackendApp.views.getUserEvents', name='get_user_events'),
    url(r'^create/event/', 'eatupBackendApp.views.createEvent', name='create_event'),
    url(r'^create/user/', 'eatupBackendApp.views.createUser', name='create_user'),
    url(r'^delete/event/', 'eatupBackendApp.views.deleteEvent', name='delete_event'),
    url(r'^delete/user/', 'eatupBackendApp.views.deleteUser', name='delete_user'),
    
    # use null for participants and locations instead of empty arrays or dicts
    # if you want to clear it entirely
    url(r'^edit/event/', 'eatupBackendApp.views.editEvent', name='edit_event'),
    
    url(r'^edit/user/', 'eatupBackendApp.views.editUser', name='edit_user'),
    
    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)

# this pattern allows django to serve media files in production
urlpatterns += patterns('',
    url(r'^media/profilePics/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.PROFILE_PICS_ROOT, 'show_indexes': True}),
)

# this pattern allows django to serve static files in production
urlpatterns += patterns('', 
    url(r'^static/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.STATIC_ROOT }),
)