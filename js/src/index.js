if (window.require) {
    window.require.config({
        map: {
            "*" : {
                "react": "https://fb.me/react-15.2.1.min.js",
                "react-dom": "https://fb.me/react-dom-15.2.1.min.js"
            }
        }
    });
}

// TODO how much of this can be stashed inside jupyter-react? 
import JupyterReact from 'jupyter-react-js';
import dispatcher from './components/dispatcher'; 
import components from './components'; 
import ComponentDOM from "./react_area";

const on_update = ( module, props ) => {
  dispatcher.dispatch({
    actionType: module.toLowerCase() + '_update',
    data: props 
  });
}

const Component = JupyterReact.Component( { on_update, components } );

const handle_kernel = function(Jupyter, kernel) {
    if ( kernel.comm_manager && !kernel.component_manager ) {
      kernel.component_manager = new JupyterReact.Manager( 'timbr.machine', kernel, Component );
    }
};

const handle_cell = function(cell) {
    if (cell.cell_type==='code') {
        const domEl = new ComponentDOM( cell );
        cell.react_dom = domEl;
    }
};

function register_events(Jupyter, events) {
    if (Jupyter.notebook && Jupyter.notebook.kernel) {
        handle_kernel(Jupyter, Jupyter.notebook.kernel);
    }
    events.on('kernel_created.Kernel kernel_created.Session', function(event, data) {
        handle_kernel(Jupyter, data.kernel);
    });

    const cells = Jupyter.notebook.get_cells();
    cells.forEach( cell => {
        handle_cell( cell );
    });

    events.on( 'create.Cell', function( event, data ) {
        handle_cell( data.cell );
    });
    events.on( 'delete.Cell', function( event, data ) {
        if ( data.cell && data.cell.widgetarea ) {
            data.cell.widgetarea.dispose();
        }
    });
}

function load_ipython_extension () {
    return new Promise(function(resolve) {
        requirejs([
            "base/js/namespace",
            "base/js/events",
            "react",
            "react-dom"
        ], function( Jupyter, events, React, ReactDom ) {
            window.React = React;
            window.ReactDom = ReactDom;
            require('./css/timbr_machine.css');
            register_events(Jupyter, events);
            resolve();
        });
    });
}

module.exports = {
  load_ipython_extension: load_ipython_extension
};
