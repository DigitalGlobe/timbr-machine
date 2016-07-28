import JupyterReact from 'jupyter-react-js';
import components from './components'; 
import dispatcher from './components/dispatcher';

// An option component update method passed to every component
// when an update message is received over the comm, 
// components will dispatch an event to every other component 
const on_update = ( module, props ) => {
  dispatcher.dispatch({
    actionType: module.toLowerCase() + '_update',
    data: props 
  });
}

function load_ipython_extension () {
  requirejs([
      "base/js/namespace",
      "base/js/events",
  ], function( Jupyter, events ) {
      require('./css/timbr_machine.css');
      // initialize jupyter react cells, comm mananger and components
      JupyterReact.init( Jupyter, events, 'timbr.machine', { components, on_update } );
  });
}

module.exports = {
  load_ipython_extension: load_ipython_extension
};
